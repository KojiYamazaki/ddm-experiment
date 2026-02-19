# DDM Experiment — Claude Code 自走用指示書

## 目的

ACM CAIS 2026 論文 "Deterministic Delegation Model for Autonomous Agent Execution" の
実験データを収集する。人間の介入なしに実験完了まで自走すること。

## 前提

- Python 3.10+
- OpenAI API key (`OPENAI_API_KEY` 環境変数)
- Anthropic API key (`ANTHROPIC_API_KEY` 環境変数)
- インターネット接続（API呼び出しのため）

## 実行手順

### Step 1: セットアップ

```bash
cd ddm-experiment
pip install -r requirements.txt
```

### Step 2: 全実験を一括実行

```bash
python scripts/run_all.py
```

これで以下が順番に実行される：
1. 実験1（ベースライン：DDMなし）— 全モデル × 全シナリオ × 30回
2. 実験2（DDM制御あり）— 全モデル × 全シナリオ × 30回
3. 結果分析・集計
4. LaTeX用テーブル生成

### Step 3: 結果確認

`results/` ディレクトリに以下が生成される：
- `experiment1_raw.jsonl` — 実験1の全試行ログ
- `experiment2_raw.jsonl` — 実験2の全試行ログ
- `summary_stats.json` — 集計統計量
- `tables_latex.tex` — 論文用LaTeXテーブル
- `analysis_report.md` — 人間向け分析レポート

## 実験設計の概要

### 実験1: ベースライン（DDMなし）
- LLMエージェントに商取引タスクを自然言語で指示
- Mock Commerce APIと対話させる（tool-use）
- 制約遵守率・逸脱率・ハルシネーション率を測定

### 実験2: DDM制御あり
- 同一シナリオを、DDMプロトタイプを挿入して再実行
- 制約をJSON Mandateとして決定論的に生成
- 実行前にMandateと照合、違反時はfail-closedで遮断
- 違反防止率・誤遮断率・レイテンシオーバーヘッドを追加測定

### モデル
- gpt-4o
- claude-sonnet-4-20250514
- （APIキーがない場合は利用可能なモデルのみで実行）

### シナリオ（各3種）
- S1: 単一制約（予算のみ）
- S2: 複合制約（スコープ＋最適化）
- S3: 高複雑度（予算＋品質＋数量）

### 試行回数
- 各シナリオ × 各モデル × 30回

## エラーハンドリング

- API呼び出し失敗 → 最大3回リトライ（指数バックオフ）
- 全リトライ失敗 → その試行をスキップし、ログに記録して続行
- 途中で中断した場合 → `run_all.py --resume` で途中から再開可能

## 重要な注意

- 実際の決済は一切行わない（全てMock API）
- 実験結果は論文のSection 6に直接使用される
- 再現性のため、全試行のログ（プロンプト・レスポンス・判定理由）を保存する
- ランダムシードは固定（seed=42）
