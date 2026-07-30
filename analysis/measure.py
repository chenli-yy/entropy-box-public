# -*- coding: utf-8 -*-
"""
论文数据测量脚本 —— 一次跑出论文里所有可从磁盘直接计算的数字。

不需要向量服务、不需要 GPU、不需要网络。只读磁盘，不写任何生产数据。

用法：
    python pipeline_free_measure.py                 # 打印摘要
    python pipeline_free_measure.py --json out.json # 同时落盘结构化结果

输出的 JSON 可直接用来刷新论文里的表格与图，编译进度推进后重跑即可。

四组测量：
  A. 查重闸门评估   —— 以已裁决台账为标注集，算精确率 / AUC / bootstrap CI / 阈值扫描
  B. 链结构         —— 链数、步数、分支率、汇合率、纯线性率
  C. 溯源完整性     —— chain_docs / retrieval_doc 引用能否在磁盘上解析
  D. 拒绝编造率     —— [待核查] 标记的分布
"""
import argparse
import json
import os
import random
import statistics
import sys
from collections import Counter

# ---------------------------------------------------------------- paths
HERE = os.path.dirname(os.path.abspath(__file__))
# 默认假设本脚本位于 <repo>/paper/analysis/，仓库根在上两级
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
TV2 = os.path.join(REPO, 'topic_v2')
REG = os.path.join(TV2, '_registry')

UNVERIFIED_MARKER = '[待核查]'


def _p(*a):
    print(*a, flush=True)


# ================================================================ A. 查重闸门
def auc_score(pos, neg):
    """相似度作为"是重复"的打分器时的 AUC（Mann-Whitney U 的等价形式）。"""
    if not pos or not neg:
        return None
    a = sum(1.0 if p > n else (0.5 if p == n else 0.0) for p in pos for n in neg)
    return a / (len(pos) * len(neg))


def bootstrap_auc_ci(pos, neg, n_boot=2000, seed=0):
    if not pos or not neg:
        return None, None
    rng = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        p = [rng.choice(pos) for _ in pos]
        n = [rng.choice(neg) for _ in neg]
        vals.append(auc_score(p, n))
    vals.sort()
    lo = vals[int(0.025 * n_boot)]
    hi = vals[int(0.975 * n_boot)]
    return lo, hi


def measure_dedup_gate():
    """把已裁决的查重台账当作标注数据集。

    标签口径：
        merged   -> 1  （裁决为真重复，已执行合并）
        resolved -> 0  （裁决为非重复，已销账）
    其余状态（open / merge_pending / merge_failed）无最终标签，排除。

    ⚠ 选择偏差：台账里只有"已经过闸门"的候选对。因此这里的 AUC 回答的是
    "在已被标记的对里，相似度能否把真重复排在前面"，而不是闸门整体的判别力。
    这正是工程上关心的问题（分数该不该参与过门之后的决策），但不可外推。
    """
    path = os.path.join(REG, '_suspects.json')
    if not os.path.exists(path):
        return {'error': 'suspects ledger not found', 'path': path}

    with open(path, encoding='utf-8') as f:
        ledger = json.load(f)

    def label(v):
        st = v.get('status')
        if st == 'merged':
            return 1
        if st == 'resolved':
            return 0
        return None

    rows = [v for v in ledger.values()
            if isinstance(v.get('sim'), (int, float)) and label(v) is not None]

    out = {
        'ledger_size': len(ledger),
        'status_distribution': dict(Counter(v.get('status') for v in ledger.values())),
        'labelled_pairs': len(rows),
        'by_metric': {},
    }

    for metric in sorted({v.get('metric') for v in rows if v.get('metric')}):
        R = [(v['sim'], label(v)) for v in rows if v.get('metric') == metric]
        pos = [x for x, y in R if y == 1]
        neg = [x for x, y in R if y == 0]
        if not R:
            continue
        a = auc_score(pos, neg)
        lo, hi = bootstrap_auc_ci(pos, neg)
        entry = {
            'n_pairs': len(R),
            'n_duplicate': len(pos),
            'n_not_duplicate': len(neg),
            'precision_at_operating_point': round(len(pos) / len(R), 4),
            'auc': round(a, 4) if a is not None else None,
            'auc_ci95': [round(lo, 4), round(hi, 4)] if lo is not None else None,
            'sim_duplicate_mean': round(statistics.mean(pos), 4) if pos else None,
            'sim_not_duplicate_mean': round(statistics.mean(neg), 4) if neg else None,
        }
        # 阈值扫描：在已标记集合内抬高阈值会发生什么
        sweep = []
        lo_t = min(x for x, _ in R)
        grid = [round(lo_t + i * (1.0 - lo_t) / 12, 3) for i in range(13)]
        for thr in grid:
            kept = [(x, y) for x, y in R if x >= thr]
            if not kept:
                continue
            d = sum(1 for _, y in kept if y == 1)
            sweep.append({
                'threshold': thr,
                'kept': len(kept),
                'duplicates_kept': d,
                'precision': round(d / len(kept), 4),
                'recall_of_duplicates': round(d / len(pos), 4) if pos else None,
            })
        entry['threshold_sweep'] = sweep
        out['by_metric'][metric] = entry

    return out


# ================================================================ B/C/D. topic 记录
def iter_topic_records():
    if not os.path.isdir(TV2):
        return
    for name in os.listdir(TV2):
        if not name.endswith('.json') or name.startswith('_'):
            continue
        path = os.path.join(TV2, name)
        try:
            with open(path, encoding='utf-8') as f:
                yield name, json.load(f)
        except Exception:
            continue


def _resolve(ref):
    """把记录里的相对路径解析成磁盘路径（记录里写的是 topic_v2/... 口径）。"""
    if not isinstance(ref, str):
        return None
    rel = ref.replace('\\', '/')
    if rel.startswith('topic_v2/'):
        rel = rel[len('topic_v2/'):]
    return os.path.join(TV2, rel)


def measure_records():
    n = 0
    chains = 0
    steps_total = 0
    step_counts = []
    branching = 0
    with_merge = 0
    linear = 0
    caps_total = 0
    assets_total = 0

    unverified_markers = 0
    topics_with_unverified = 0

    cd_refs = 0
    cd_missing = 0
    topics_without_cd = 0
    rd_refs = 0
    rd_missing = 0

    for _, d in iter_topic_records():
        n += 1
        raw = json.dumps(d, ensure_ascii=False)

        u = raw.count(UNVERIFIED_MARKER)
        unverified_markers += u
        if u:
            topics_with_unverified += 1

        caps_total += len(d.get('capabilities') or [])
        assets_total += len(d.get('assets') or [])

        for c in d.get('task_chains') or []:
            chains += 1
            st = c.get('steps') or []
            step_counts.append(len(st))
            steps_total += len(st)
            has_branch = any(len(s.get('next') or []) > 1 for s in st)
            has_merge = any(s.get('is_merge') for s in st)
            if has_branch:
                branching += 1
            if has_merge:
                with_merge += 1
            if not has_branch and not has_merge:
                linear += 1

        cds = d.get('chain_docs') or []
        if not cds:
            topics_without_cd += 1
        for ref in cds:
            p = _resolve(ref)
            if p is None:
                continue
            cd_refs += 1
            if not os.path.exists(p):
                cd_missing += 1

        rd = d.get('retrieval_doc')
        p = _resolve(rd)
        if p is not None:
            rd_refs += 1
            if not os.path.exists(p):
                rd_missing += 1

    if n == 0:
        return {'error': 'no topic records found', 'path': TV2}

    step_counts.sort()

    def pct(a, b):
        return round(100.0 * a / b, 2) if b else None

    return {
        'topic_records': n,
        'capability_entries': caps_total,
        'asset_entries': assets_total,
        'chains': {
            'total': chains,
            'per_topic_mean': round(chains / n, 2),
            'steps_total': steps_total,
            'steps_per_chain_mean': round(steps_total / chains, 2) if chains else None,
            'steps_per_chain_median': step_counts[len(step_counts) // 2] if step_counts else None,
            'steps_per_chain_p90': step_counts[int(0.9 * len(step_counts))] if step_counts else None,
            'branching': branching,
            'branching_pct': pct(branching, chains),
            'with_merge_node': with_merge,
            'with_merge_node_pct': pct(with_merge, chains),
            'purely_linear': linear,
            'purely_linear_pct': pct(linear, chains),
        },
        'provenance_integrity': {
            'chain_doc_references': cd_refs,
            'chain_doc_missing': cd_missing,
            'chain_doc_resolvable_pct': pct(cd_refs - cd_missing, cd_refs),
            'topics_without_chain_docs': topics_without_cd,
            'topics_without_chain_docs_pct': pct(topics_without_cd, n),
            'retrieval_doc_references': rd_refs,
            'retrieval_doc_missing': rd_missing,
            'retrieval_doc_resolvable_pct': pct(rd_refs - rd_missing, rd_refs),
        },
        'refusal_to_fabricate': {
            'unverified_markers_total': unverified_markers,
            'topics_with_unverified': topics_with_unverified,
            'topics_with_unverified_pct': pct(topics_with_unverified, n),
            'markers_per_topic_mean': round(unverified_markers / n, 2),
        },
    }


# ================================================================ 摊销比
def measure_amortization():
    """alpha = |U| / |C| —— 每个编译单元被多少个主题消费。

    以活注册表内的实体为准，避免把已下线实体的边计进来。
    """
    import sqlite3
    db = os.path.join(REG, 'ontology_registry.db')
    hier = os.path.join(REG, '_hierarchy.json')
    if not (os.path.exists(db) and os.path.exists(hier)):
        return {'error': 'registry db or hierarchy not found'}

    con = sqlite3.connect('file:%s?mode=ro' % db.replace('\\', '/'), uri=True)
    live = {r[0] for r in con.execute('select id from capabilities')}
    con.close()

    with open(hier, encoding='utf-8') as f:
        h = {k: v for k, v in json.load(f).items() if k in live}

    usages = [len(v.get('used_by_topics') or []) for v in h.values()]
    C = len(h)
    U = sum(usages)
    dist = Counter(usages)
    reused = sum(1 for u in usages if u > 1)

    # 摊销曲线：随机编译顺序下 alpha 随已编译主题数的增长
    t2c = {}
    for cid, v in h.items():
        for t in v.get('used_by_topics') or []:
            t2c.setdefault(t, set()).add(cid)
    topics = sorted(t2c)
    rng = random.Random(1)
    curves = []
    for _ in range(20):
        order = topics[:]
        rng.shuffle(order)
        seen, used, pts = set(), 0, []
        for i, t in enumerate(order, 1):
            used += len(t2c[t])
            seen |= t2c[t]
            if i % 50 == 0 or i == len(order):
                pts.append((i, used / len(seen)))
        curves.append(pts)
    xs = [p[0] for p in curves[0]]
    mean_curve = [(x, round(sum(c[i][1] for c in curves) / len(curves), 4))
                  for i, x in enumerate(xs)]

    return {
        'distinct_capabilities': C,
        'capability_topic_usages': U,
        'amortization_factor': round(U / C, 4) if C else None,
        'rederivations_avoided': U - C,
        'reused_across_topics': reused,
        'reused_pct': round(100.0 * reused / C, 2) if C else None,
        'max_reuse': max(usages) if usages else 0,
        'usage_distribution_head': dict(sorted(dist.items())[:12]),
        'amortization_curve': mean_curve,
    }


# ================================================================ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', help='把结构化结果写到这个文件')
    ap.add_argument('--repo', help='仓库根目录（默认按脚本位置推断）')
    args = ap.parse_args()

    if args.repo:
        global REPO, TV2, REG
        REPO = os.path.abspath(args.repo)
        TV2 = os.path.join(REPO, 'topic_v2')
        REG = os.path.join(TV2, '_registry')

    result = {
        'repo': REPO,
        'dedup_gate': measure_dedup_gate(),
        'records': measure_records(),
        'amortization': measure_amortization(),
    }

    # ---------- 摘要 ----------
    _p('=' * 68)
    _p('A. 查重闸门评估（以已裁决台账为标注集）')
    dg = result['dedup_gate']
    if 'error' in dg:
        _p('  ', dg['error'])
    else:
        _p('  台账 %d 条，其中有最终标签 %d 条' % (dg['ledger_size'], dg['labelled_pairs']))
        for m, e in dg['by_metric'].items():
            _p('  [%s] n=%d  真重复=%d  精确率=%.3f  AUC=%.3f  CI95=%s'
               % (m, e['n_pairs'], e['n_duplicate'],
                  e['precision_at_operating_point'], e['auc'] or 0, e['auc_ci95']))

    _p('')
    _p('B/C/D. 编译产物')
    rc = result['records']
    if 'error' in rc:
        _p('  ', rc['error'])
    else:
        ch = rc['chains']
        _p('  主题记录 %d  能力条目 %d  资产条目 %d'
           % (rc['topic_records'], rc['capability_entries'], rc['asset_entries']))
        _p('  链 %d（%.2f/主题）  步 %.2f/链（中位 %s）'
           % (ch['total'], ch['per_topic_mean'],
              ch['steps_per_chain_mean'], ch['steps_per_chain_median']))
        _p('  分支 %.1f%%   含汇合 %.1f%%   纯线性 %.1f%%'
           % (ch['branching_pct'], ch['with_merge_node_pct'], ch['purely_linear_pct']))
        pi = rc['provenance_integrity']
        _p('  溯源：chain_doc 引用 %d，可解析 %.2f%%（缺 %d）；无 chain_docs 的主题 %d'
           % (pi['chain_doc_references'], pi['chain_doc_resolvable_pct'],
              pi['chain_doc_missing'], pi['topics_without_chain_docs']))
        rf = rc['refusal_to_fabricate']
        _p('  未核查标记 %d 处，%.1f%% 的主题至少含一处（均值 %.2f/主题）'
           % (rf['unverified_markers_total'], rf['topics_with_unverified_pct'],
              rf['markers_per_topic_mean']))

    _p('')
    _p('E. 摊销比')
    am = result['amortization']
    if 'error' in am:
        _p('  ', am['error'])
    else:
        _p('  |C|=%d  |U|=%d  alpha=%.3f  省下推导 %d 次  最高复用 %d'
           % (am['distinct_capabilities'], am['capability_topic_usages'],
              am['amortization_factor'], am['rederivations_avoided'], am['max_reuse']))
    _p('=' * 68)

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        _p('结构化结果已写入 %s' % args.json)


if __name__ == '__main__':
    sys.exit(main())
