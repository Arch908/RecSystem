"""Run ranking, diversity, and coverage evaluation and tune hybrid weights."""
from pathlib import Path
from ml.evaluation import evaluate_movielens, save_results

ROOT=Path(__file__).resolve().parent
results=evaluate_movielens(ROOT/'data'/'ratings.csv', ROOT/'data'/'movies.csv', k=10, max_users=200, random_state=42)
out=ROOT/'evaluation_results.json'
save_results(results,out)
print(f'Saved: {out}')
for row in results['results']:
    print(
        f"{row['method']:18s} "
        f"P@{row['k']}={row['precision_at_k']:.4f} "
        f"R@{row['k']}={row['recall_at_k']:.4f} "
        f"F1@{row['k']}={row['f1_at_k']:.4f} "
        f"NDCG@{row['k']}={row['ndcg_at_k']:.4f} "
        f"DIV={row['diversity_at_k']:.4f} COV={row['coverage']:.4f}"
    )
print('Recommended weights:', results.get('recommended_weights'))
