import json
import csv
from ranx import Qrels, Run, evaluate
from backend.api.main import rank_trials, RankRequest, PatientProfile


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
def build_run(queries):
    run = {}
    for qid, profile_json in queries.items():
        profile_json = sanitize_profile_json(profile_json)

        profile = PatientProfile(**profile_json)
        request = RankRequest(profile=profile)
        result = rank_trials(request)

        run[qid] = {
            hit.nct_id: float(hit.score)
            for hit in result.hits
        }
    return run


# --------------------------------------------------------
# Main evaluation
# --------------------------------------------------------
queries = load_queries_csv("./backend/evaluation/converted_queries_using_openai.csv")
qrels = load_qrels_tsv("./backend/evaluation/qrels_trec.tsv")
run = build_run(queries)

extended_metrics = [
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

results = evaluate(
    qrels=Qrels.from_dict(qrels),
    run=Run.from_dict(run),
    metrics=extended_metrics,
)

# Core summary
core_keys = ["mrr@10", "ndcg@10", "precision@10", "recall@100"]
core = {k: results.get(k) for k in core_keys if k in results}

print("\n=== Core Metrics ===")
for k in core_keys:
    if k in core:
        print(f"{k}: {core[k]:.4f}")

print("\n=== Extended Metrics ===")
for k in extended_metrics:
    if k in results:
        print(f"{k}: {results[k]:.4f}")

# Save to files for tracking
try:
    import os
    import pandas as pd
    out_dir = "./backend/evaluation"
    os.makedirs(out_dir, exist_ok=True)

    # JSON
    json_path = os.path.join(out_dir, "results.json")
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump({"core": core, "extended": results}, jf, indent=2)

    # CSV
    csv_path = os.path.join(out_dir, "results.csv")
    df = pd.DataFrame([{**{"metric": k, "value": results[k]}, **({"core": k in core_keys})} for k in results])
    df.to_csv(csv_path, index=False)

    print(f"\nSaved results to: {json_path} and {csv_path}")
except Exception as e:
    print(f"Warning: could not save results: {e}")
