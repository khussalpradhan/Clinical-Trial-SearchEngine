import json
import csv
from ranx import Qrels, Run, evaluate
from backend.api.main import rank_trials, RankRequest, PatientProfile
from backend.evaluation.custom_metrics import compute_all_feasibility_metrics
import os
import matplotlib.pyplot as plt

# --------------------------------------------------------
# Load queries CSV (Raw Text)
# --------------------------------------------------------
def load_queries_csv(path):
    queries = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qid = row["id"].strip()
            text = row["text"].strip()
            queries[qid] = text
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


# --------------------------------------------------------
# Build run using your ranker (Direct Text Query)
# --------------------------------------------------------
def build_run(queries):
    run = {}
    hit_metadata = {}

    for qid, text in queries.items():
        # Create a profile with optional fields as None
        # This triggers "Case 1: Description Only" logic in backend
        profile = PatientProfile(
            age=None,
            gender=None,
            conditions=[],
            biomarkers=[],
            history=[],
            labs={},
            ecog=None,
            prior_lines=None,
            days_since_last_treatment=None
        )
        
        # Pass the raw text as 'query'
        request = RankRequest(
            profile=profile,
            query=text
        )
        
        try:
            result = rank_trials(request)
        except Exception as e:
            print(f"Error processing query {qid}: {e}")
            continue

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
if __name__ == "__main__":
    print("Loading queries from CSV...")
    queries = load_queries_csv("./backend/evaluation/queries.csv")
    print(f"Loaded {len(queries)} queries.")
    
    print("Loading QRELs...")
    qrels = load_qrels_tsv("./backend/evaluation/qrels_trec.tsv")
    print(f"Loaded QRELs for {len(qrels)} queries.")
    
    print("Running search...")
    run, hit_metadata = build_run(queries)
    print("Search complete.")

    print("Evaluating...")
    ranking_results = evaluate(
        qrels=Qrels.from_dict(qrels),
        run=Run.from_dict(run),
        make_comparable=True,
        
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
    )
    
    feasibility_results = compute_all_feasibility_metrics(qrels, run, hit_metadata)

    OUTPUT_CSV   = "metrics_report_direct.csv"
    OUTPUT_JSON  = "metrics_report_direct.json"
    CHART_DIR    = "metrics_charts_direct"

    all_results = {
        **ranking_results,
        **feasibility_results
    }

    print("\n========= FINAL METRICS (BM25+ Dense Retrieval) =========")
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

    save_bar_chart("Main Ranking Metrics (Direct)", ranking_subset, "ranking_metrics.png")

    # --- Chart 2: Feasibility Metrics ---
    save_bar_chart("Feasibility Metrics (Direct)", feasibility_results, "feasibility_metrics.png")

    print("\nCharts saved in:", CHART_DIR)
