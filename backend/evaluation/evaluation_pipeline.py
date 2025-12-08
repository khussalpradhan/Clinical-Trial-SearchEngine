import json
import csv
from ranx import Qrels, Run, evaluate
from backend.api.main import rank_trials, RankRequest, PatientProfile
from backend.evaluation.custom_metrics import  compute_all_feasibility_metrics
import os
import matplotlib.pyplot as plt

# --------------------------------------------------------
# Load queries CSV
# --------------------------------------------------------
def load_queries_csv(path):
    queries = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qid = row["id"].strip()
            profile_json = json.loads(row["json_using_openai"])
            queries[qid] = profile_json
    return queries


# --------------------------------------------------------
# Load TSV qrels
# --------------------------------------------------------
def load_qrels_tsv(path):
    qrels = {}
    with open(path, "r", encoding="utf-8") as f:
        next(f)
        for line in f:
            qid, docid, rel = line.strip().split("\t")
            rel = int(rel)
            if qid not in qrels:
                qrels[qid] = {}
            qrels[qid][docid] = rel
    return qrels

def sanitize_profile_json(profile_json):
    cleaned = dict(profile_json)

    # ---------------------------
    # 1. Gender fallback
    # ---------------------------
    if "gender" not in cleaned or not cleaned["gender"]:
        cleaned["gender"] = "Unknown"

    # ---------------------------
    # 2. Fix age if it's a float or invalid
    # ---------------------------
    age = cleaned.get("age")
    if isinstance(age, float):
        cleaned["age"] = int(age) if age > 1 else 1
    elif age is None:
        cleaned["age"] = 1

    # ---------------------------
    # 3. Clean labs (remove non-numeric values)
    # ---------------------------
    fixed_labs = {}
    for key, val in cleaned.get("labs", {}).items():
        try:
            fixed_labs[key] = float(val)
        except:
            fixed_labs[key] = None   # drop invalid values

    cleaned["labs"] = fixed_labs

    return cleaned


# --------------------------------------------------------
# Build run using your ranker
# --------------------------------------------------------
# def build_run(queries):
#     run = {}
#     for qid, profile_json in queries.items():
#         profile_json = sanitize_profile_json(profile_json)

#         profile = PatientProfile(**profile_json)
#         request = RankRequest(profile=profile)
#         result = rank_trials(request)

#         run[qid] = {
#             hit.nct_id: float(hit.score)
#             for hit in result.hits
#         }
#     return run



def build_run(queries):
    run = {}
    hit_metadata = {}

    for qid, profile_json in queries.items():
        profile_json = sanitize_profile_json(profile_json)
        profile = PatientProfile(**profile_json)
        request = RankRequest(profile=profile)
        result = rank_trials(request)

        run[qid] = {}
        hit_metadata[qid] = {}

        for hit in result.hits:
            run[qid][hit.nct_id] = float(hit.score)

            # store feasibility metadata
            hit_metadata[qid][hit.nct_id] = {
                "feasibility_score": float(hit.feasibility_score or 0.0),
                "is_feasible": bool(hit.is_feasible),
            }

    return run, hit_metadata

# --------------------------------------------------------
# Main evaluation
# --------------------------------------------------------
queries = load_queries_csv("./backend/evaluation/converted_queries_using_openai.csv")
qrels = load_qrels_tsv("./backend/evaluation/qrels_trec.tsv")
run, hit_metadata = build_run(queries)

ranking_results = evaluate(
    qrels=Qrels.from_dict(qrels),
    run=Run.from_dict(run),
    
    # metrics=["mrr@10", "ndcg@10", "recall@100"]
    metrics = [
    # ranking metrics
    "mrr@10",
    "ndcg@3", "ndcg@5", "ndcg@10", "ndcg@20",
    "map@10",

    # precision / recall
    "precision@1", "precision@3", "precision@5", "precision@10", "precision@20",
    "recall@5", "recall@10", "recall@20", "recall@100",

    # others
    "hit_rate@1", "hit_rate@5", "hit_rate@10",
    "f1@5", "f1@10", "f1@20",
    "bpref",
   ]

        
    # custom_metrics=get_custom_metrics(hit_metadata)

)



feasibility_results = compute_all_feasibility_metrics(qrels, run, hit_metadata)

# print("\nRanking Metrics (Ranx):")
# print(results)

# print("\nFeasibility Metrics:")
# print(feasibility_results)


OUTPUT_CSV   = "metrics_report.csv"
OUTPUT_JSON  = "metrics_report.json"
CHART_DIR    = "metrics_charts"

all_results = {
    **ranking_results,
    **feasibility_results
}

print("\n========= FINAL METRICS (Complete Model) =========")
for k, v in all_results.items():
    print(f"{k}: {v}")


# =========================================================
#        5. SAVE RESULTS (CSV + JSON)
# =========================================================
print(f"\nSaving CSV to {OUTPUT_CSV} ...")

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["metric", "value"])
    for metric, value in all_results.items():
        writer.writerow([metric, float(value)])

print(f"Saving JSON to {OUTPUT_JSON} ...")

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)

os.makedirs(CHART_DIR, exist_ok=True)

def save_bar_chart(title, values, filename):
    plt.figure(figsize=(10, 6))
    plt.bar(values.keys(), values.values())
    plt.xticks(rotation=45, ha='right')
    plt.title(title)
    plt.tight_layout()
    plt.savefig(os.path.join(CHART_DIR, filename))
    plt.close()


# --- Chart 1: Ranking Metrics ---
ranking_subset = {
    k: float(ranking_results[k])
    for k in ["mrr@10", "ndcg@10", "map@10",
              "precision@10", "recall@10", "f1@10"]
}

save_bar_chart("Main Ranking Metrics", ranking_subset, "ranking_metrics.png")

# --- Chart 2: Feasibility Metrics ---
save_bar_chart("Feasibility Metrics", feasibility_results, "feasibility_metrics.png")

print("\nCharts saved in:", CHART_DIR)