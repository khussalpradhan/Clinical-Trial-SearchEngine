# # backend/evaluation/custom_metrics.py

# from ranx import register_custom_metric


# def precision_feasible(qid, ranked_list, qrels, K, hit_metadata):
#     """
#     Precision(feasible)@K = (# feasible AND relevant in top-K) / K
#     """
#     top_k = ranked_list[:K]

#     feasible_rel = 0
#     for doc_id in top_k:
#         rel = qrels.get(qid, {}).get(doc_id, 0)
#         is_rel = rel > 0

#         is_feasible = hit_metadata[qid][doc_id]["is_feasible"]

#         if is_rel and is_feasible:
#             feasible_rel += 1

#     return feasible_rel / K


# def recall_feasible(qid, ranked_list, qrels, K, hit_metadata):
#     """
#     Recall(feasible)@K = (# feasible AND relevant in top-K) / (# all relevant)
#     """
#     relevant_docs = [d for d, r in qrels.get(qid, {}).items() if r > 0]
#     if not relevant_docs:
#         return 0.0

#     feasible_rel = 0

#     for doc_id in ranked_list[:K]:
#         if doc_id not in relevant_docs:
#             continue

#         if hit_metadata[qid][doc_id]["is_feasible"]:
#             feasible_rel += 1

#     return feasible_rel / len(relevant_docs)


# def violation(qid, ranked_list, qrels, K, hit_metadata):
#     """
#     Violation@K = (# infeasible in top-K) / K
#     """
#     top_k = ranked_list[:K]
#     violations = sum(
#         1 for doc_id in top_k
#         if hit_metadata[qid][doc_id]["is_feasible"] is False
#     )
#     return violations / K


# def reach(qid, ranked_list, qrels, K, hit_metadata):
#     """
#     Reach@K = (# feasible AND relevant in top-K) / (# relevant)
#     (same as recall_feasible but returned as REACH)
#     """
#     relevant_docs = [d for d, r in qrels.get(qid, {}).items() if r > 0]
#     if not relevant_docs:
#         return 0.0

#     feasible_rel = 0
#     for doc_id in ranked_list[:K]:
#         if doc_id in relevant_docs and hit_metadata[qid][doc_id]["is_feasible"]:
#             feasible_rel += 1

#     return feasible_rel / len(relevant_docs)


# # ----------------------------------------------------------
# # Provide a Ranx-ready wrapper
# # ----------------------------------------------------------
# def get_custom_metrics(hit_metadata):
#     """
#     hit_metadata structure:
#     hit_metadata[qid][doc_id] = { "is_feasible": bool, "feasibility_score": float }
#     """

#     return {
#         "precision_feasible": lambda qid, run, qrels, K:
#             precision_feasible(qid, run[qid], qrels, K, hit_metadata),

#         "recall_feasible": lambda qid, run, qrels, K:
#             recall_feasible(qid, run[qid], qrels, K, hit_metadata),

#         "violation": lambda qid, run, qrels, K:
#             violation(qid, run[qid], qrels, K, hit_metadata),

#         "reach": lambda qid, run, qrels, K:
#             reach(qid, run[qid], qrels, K, hit_metadata),
#     }



# from ranx import register_custom_metric

# def precision_feasible_func(qid, run, qrels, k, hit_metadata):
#     return precision_feasible(qid, run[qid], qrels, k, hit_metadata)

# def recall_feasible_func(qid, run, qrels, k, hit_metadata):
#     return recall_feasible(qid, run[qid], qrels, k, hit_metadata)

# def violation_func(qid, run, qrels, k, hit_metadata):
#     return violation(qid, run[qid], qrels, k, hit_metadata)

# def reach_func(qid, run, qrels, k, hit_metadata):
#     return reach(qid, run[qid], qrels, k, hit_metadata)

# def register_all_custom_metrics(hit_metadata):
#     register_custom_metric(
#         name="precision_feasible",
#         fn=lambda qid, run, qrels, k: precision_feasible_func(qid, run, qrels, k, hit_metadata)
#     )

#     register_custom_metric(
#         name="recall_feasible",
#         fn=lambda qid, run, qrels, k: recall_feasible_func(qid, run, qrels, k, hit_metadata)
#     )

#     register_custom_metric(
#         name="violation",
#         fn=lambda qid, run, qrels, k: violation_func(qid, run, qrels, k, hit_metadata)
#     )

#     register_custom_metric(
#         name="reach",
#         fn=lambda qid, run, qrels, k: reach_func(qid, run, qrels, k, hit_metadata)
#     )


# backend/evaluation/feasibility_metrics.py

def precision_feasible_at_k(qid, run, qrels, hit_metadata, K):
    ranked = list(run[qid].keys())[:K]
    count = 0
    for docid in ranked:
        if qrels.get(qid, {}).get(docid, 0) > 0 and hit_metadata[qid][docid]["is_feasible"]:
            count += 1
    return count / K


def recall_feasible_at_k(qid, run, qrels, hit_metadata, K):
    relevant = [d for d, r in qrels.get(qid, {}).items() if r > 0]
    if not relevant:
        return 0.0

    ranked = list(run[qid].keys())[:K]
    count = 0

    for docid in ranked:
        if docid in relevant and hit_metadata[qid][docid]["is_feasible"]:
            count += 1

    return count / len(relevant)


def violation_at_k(qid, run, hit_metadata, K):
    ranked = list(run[qid].keys())[:K]
    count = 0
    for docid in ranked:
        if not hit_metadata[qid][docid]["is_feasible"]:
            count += 1
    return count / K


def reach_at_k(qid, run, qrels, hit_metadata, K):
    return recall_feasible_at_k(qid, run, qrels, hit_metadata, K)


def compute_all_feasibility_metrics(qrels, run, hit_metadata):
    out = {
        "precision_feasible@10": [],
        "recall_feasible@20": [],
        "violation@5": [],
        "reach@10": [],
    }

    for qid in run:
        out["precision_feasible@10"].append(
            precision_feasible_at_k(qid, run, qrels, hit_metadata, 10)
        )
        out["recall_feasible@20"].append(
            recall_feasible_at_k(qid, run, qrels, hit_metadata, 20)
        )
        out["violation@5"].append(
            violation_at_k(qid, run, hit_metadata, 5)
        )
        out["reach@10"].append(
            reach_at_k(qid, run, qrels, hit_metadata, 10)
        )

    # return means
    return {metric: sum(vals) / len(vals) for metric, vals in out.items()}
