# POINT 0 — 統合版

## Deterministic Delegation Model for Autonomous Agent Execution

**Submission Strategy for ACM Conference on AI and Agentic Systems (CAIS 2026)**

---

## 1. 本ドキュメントの目的

本ドキュメントは、ACM CAIS 2026への論文提出という単一目的に対する**基準点（Point 0）**である。

これまでの構想（TrustKit設計議論、技術検証プラン、Point 0初版）を統合し、
今後の作業すべてがここに立ち返る参照基準とする。

明確化する事項：
- 対象カンファレンスの性質と、それに対する論文の位置づけ
- 中心概念の定義（AEG / DDM / Trust Gap）
- 論文構成・実験設計・スケジュール
- 成功の定義
- やらないことの明示

---

## 2. 対象カンファレンスの性質

ACM CAIS 2026は、LLM性能向上ではなく**エージェントシステムの設計・検証・運用**に焦点を置く。

CFPの5ピラーのうち、本論文が直接対応するのは以下の2つである。

**第一適合：Security & Privacy**
- "Verification and certification of secure agentic behaviors"
- "Alignment and safety in autonomous agents"
- "Security and privacy in multi-agent architectures"

**第二適合：Engineering & Operations**
- "Specification languages and verification frameworks"
- "Security and safety in multi-component systems"

したがって本論文は、
- Alignment理論でもなく
- Identity標準化でもなく
- 経済プロトコルの議論でもなく

**自律エージェントの実行制御における、委任の決定論的モデルとその実証**

として位置づける。

---

## 3. 用語体系の整理

本論文では3つの概念を階層的に用いる。混同しない。

### 3.1 Trust Gap（問題の名前）

Identity/IAM層（「誰がアクセスできるか」）とTool/API実行層（「何が呼べるか」）の間に存在する構造的空白。

具体的には以下が欠落している：
- 誰の意思で（Under whose intent）AIがこの実行をしたか
- どの制約下で（With what limits）許可されたか
- なぜ許可されたか（Why allowed）を第三者が再構成できるか

Trust Gapは**問題そのものの名前**であり、論文のMotivationセクションで定義する。

### 3.2 Deterministic Delegation Model / DDM（解法の名前）

Trust Gapを埋めるための形式モデル。本論文の核心的貢献。

委任（Mandate）を静的トークンとして扱うのではなく、
**観測可能な入力から決定論的に生成される関数出力**として扱う。

```
M = f(u, cap, r, ctx, p_v)

  u    = 委任主体（Principal）
  cap  = 能力クラス（Capability Class）
  r    = 対象リソース（Resource）
  ctx  = 観測可能なコンテキスト（Observable Context）
  p_v  = バージョン固定されたポリシー（Versioned Policy）
```

**DDMの決定的性質（本論文で証明すべきこと）：**

1. **再現性（Reproducibility）：** 同一入力 → 同一Mandate。いつ・誰が再計算しても同じ結果になる
2. **非権威性（Non-authoritativeness）：** Mandate自体は権限の源泉ではない。入力条件の派生物（derived artifact）である
3. **一時性（Ephemerality）：** Mandateは保存・管理の対象ではなく、必要時に再生成される
4. **Fail-closed性：** 有効なMandateなしには実行経路が存在しない

### 3.3 Autonomous Execution Governance / AEG（領域の名前）

DDMを含む、より広い研究領域の概念。

**本論文ではAEGを全面展開しない。** 
Introductionで将来的な射程として言及し、DDMがその中核構成要素であることを示すにとどめる。
AEGの領域宣言は次段階で行う。

---

## 4. 論文の貢献（Contribution Statement）

本論文は以下の3点を貢献として主張する。

**C1. Trust Gapの形式的定義**
自律エージェント実行における、Policy Decision層とExecution層の間の構造的空白を形式的に定義する。既存研究が個別に扱ってきた問題（アクセス制御、ランタイム検証、監査）が、この空白によって統合的に解けていないことを示す。

**C2. Deterministic Delegation Model（DDM）**
Trust Gapを埋める形式モデルを提案する。委任を決定論的関数の出力として扱うことで、非決定的なエージェント推論を内部に閉じ込めつつ、実行境界では決定論的な制御・説明責任を成立させる。

**C3. 実証評価**
商取引（Agentic Commerce）を実験ドメインとして、(a) 制御なし状態での意図-実行乖離率のベースライン、(b) DDMベースの制御による乖離率の低減効果を定量的に示す。

---

## 5. 射程の明示（スコープ）

### 扱うこと
- 自律エージェントにおける委任の曖昧性の問題定義
- 決定論的委任生成の形式モデル（DDM）
- 実行境界アーキテクチャの設計
- プロトタイプ実装
- 最小限の実証評価（2実験）

### 扱わないこと
- AI法的人格の議論
- DID/VC標準化の詳細
- 経済プロトコル（AP2/ACP）の設計
- Alignment理論・RLHF
- 独自ID標準・独自Policy言語の提案
- LLMの安全化・プロンプト制御

---

## 6. 既存研究との差別化（Related Workの骨格）

Related WorkはSection 3（Problem Formulationの直後）に配置し、
**「この空白は誰も埋めていない」ことを査読者に早期に確信させる。**

### 差別化マトリクス

| 研究系統 | 代表例 | 解いていること | 未解決（DDMが埋める） |
|---|---|---|---|
| Specification / Policy | OPA, Cedar, Rego | Allow/Deny判断 | 実行時enforcement、委任の決定論的生成 |
| Runtime Enforcement | AgentSpec (ICSE 2026) | 単一エージェントの実行時検証 | 委任主体の区別、商用環境での検証、監査一体化 |
| Delegation / AuthZ | Keycard.ai, ZCAP-LD, OAuth OBO | アクセス権限の委譲 | 意味的整合性（意図 vs 実行の乖離）、再現可能な説明責任 |
| Agent Safety | OWASP Agentic Top 10 | リスク列挙・脅威モデル | 実装レベルの防止メカニズム |
| Audit / Provenance | Secure logging, Blockchain audit | 事後検証 | 実行時制御との一体化、「なぜ許可されたか」の説明 |

### 空白の定式化

以下の5条件を**同時に**満たす研究・フレームワークは2025年時点で存在しない：
1. 非決定的な意思決定を前提とし
2. 実行時に決定論的enforcementを行い
3. 委任（誰の意思か）を明示し
4. その理由を証拠として再構成可能にし
5. 実運用（SaaS / API / Tool）に適用可能

DDMはこの交差点に位置する。

---

## 7. 論文構成（9ページ、固定）

途中で拡張しない。

```
Section 1. Introduction                          (~1.5 pages)
  - エージェントが実行主体になる時代の到来
  - Trust Gapの概要提示
  - 貢献の要約（C1, C2, C3）
  - AEGへの言及（射程の示唆のみ）

Section 2. Problem Formulation                    (~1 page)
  - Trust Gapの形式的定義
  - Intent → Mandate → Execution → Outcome の遷移モデル
  - 各遷移における乖離リスクの分類
  - Fail-closed要件の定式化
  - 動機シナリオ（商取引での具体的失敗例）

Section 3. Related Work                           (~1.5 pages)
  - 5系統の整理（上記マトリクス）
  - 各系統の到達点と限界
  - 5条件の空白の明示
  - DDMの学術的ポジショニング

Section 4. Deterministic Delegation Model         (~1.5 pages)
  - DDMの形式定義：M = f(u, cap, r, ctx, p_v)
  - 4つの性質の定義と証明スケッチ
    (再現性、非権威性、一時性、Fail-closed性)
  - 設計判断：Mandateは派生物であり管理対象ではない
  - 既存エコシステムとの統合モデル
    (IdP → Policy Engine → DDM → Agent → Tool)

Section 5. Architecture & Prototype               (~1 page)
  - DDMを実現するアーキテクチャの概要
    （全5コンポーネントを記述するが、DDMに直接関わる
     Delegation Module + Execution Bindingを重点的に）
  - プロトタイプ実装の技術的詳細

Section 6. Evaluation                             (~1.5 pages)
  - 実験設計（2実験：ベースライン＋DDM制御）
  - 環境・シナリオ・指標
  - 結果と分析

Section 7. Discussion & Limitations               (~0.5 pages)
  - 制約・限界の率直な記述
  - 汎用性（決済以外への適用可能性）
  - AEGへの発展可能性

Section 8. Conclusion                             (~0.5 pages)
```

---

## 8. 実験設計

### 8.1 設計方針

9日間という制約下で、**DDMの有効性を示す最小限かつ説得力のある実験**を行う。
大規模な実証ではなく「問題の存在証明 + 制御の有効性の初期証拠」を狙う。

### 8.2 実験ドメイン：Agentic Commerce

商取引を選ぶ理由：意図-実行の乖離が**金銭的損失**として最も明確に定量化できるため。
ただし論文ではこれがDDMの一適用例であり、インフラ操作・契約締結等にも適用可能であることを明記する。

### 8.3 実験1：ベースライン（DDMなし）

**目的：** 制御なし状態で、AIエージェントがどの程度「意図と異なる実行」を行うかの定量化。

**方法：**
- 複数のLLM（GPT-4o, Claude 3.5 Sonnet, 他1-2モデル）
- 商取引タスクを自然言語で指示（制約条件を含む）
- Tool-use機能でMock Commerce APIと対話させる

**シナリオ：**
| ID | 指示（自然言語） | 制約種別 | 複雑度 |
|---|---|---|---|
| S1 | 「3万円以下のカメラを買って」 | 単一制約（予算） | Low |
| S2 | 「A社製品のみ比較して最安を選んで」 | 複合制約（スコープ＋最適化） | Medium |
| S3 | 「予算5万円以内で、レビュー4.0以上、2個注文」 | 複合制約（予算＋品質＋数量） | High |

**試行：** 各シナリオ × 各LLM × 30回（N=30 per condition）

**測定指標：**
- **Constraint Compliance Rate (CCR):** 全制約を遵守した実行の割合
- **Silent Deviation Rate (SDR):** ユーザーに通知せず制約を逸脱した割合
- **Hallucination Rate (HR):** 存在しない商品・価格を生成した割合

### 8.4 実験2：DDM制御あり

**目的：** DDMベースのExecution Controlが乖離をどの程度低減するかの測定。

**方法：**
- 実験1と同一シナリオ・同一LLMで再実行
- DDMプロトタイプを挿入：
  - 制約をJSON形式のMandateとして決定論的に生成
  - 実行前に各APIリクエストをMandateと照合
  - 違反時はfail-closedで遮断（実行を停止しユーザーに通知）

**追加測定指標：**
- **Violation Prevention Rate (VPR):** DDMが遮断した違反の割合
- **False Rejection Rate (FRR):** 正常な実行を誤って遮断した割合
- **Latency Overhead:** DDM検証による追加レイテンシ（ms）
- **Audit Reproducibility:** ログからMandateを再計算し、実行判断を再現できるか（binary）

### 8.5 実験環境

```
[User Intent (NL)]
    → [Intent Parser (LLM)]
    → [DDM: Mandate Generator (deterministic function)]
    → [Agent (LLM + Tool Use)]
    → [DDM: Execution Binding (constraint checker)]
    → [Mock Commerce API]
    → [Audit Log]
         → [Mandate Reproducer (post-hoc verification)]
```

- Mock Commerce API：商品カタログ＋APIレスポンスのシミュレーション（実決済なし）
- 全リクエスト/レスポンスをログに記録
- 実験後にAudit Logからの再現性検証を実施

---

## 9. Abstract（登録用ドラフト）

> **Deterministic Delegation Model for Autonomous Agent Execution**
>
> As AI agents evolve from advisory tools into autonomous execution entities—conducting financial transactions, configuring infrastructure, and negotiating contracts—a structural gap emerges between existing architectural layers. Identity systems establish *who* an agent is; policy engines determine *what* it may do. Yet neither guarantees *under whose intent* an agent acts, *within what bounds* it operates at execution time, or *why* a particular action was permitted—in a manner that can be deterministically reconstructed after the fact. We term this the **Trust Gap**.
>
> We propose the **Deterministic Delegation Model (DDM)**, a formal model that treats delegation not as a static token but as the output of a deterministic function over observable inputs: the delegating principal, capability class, target resource, context, and versioned policy. DDM ensures that mandates are reproducible, ephemeral, non-authoritative, and enforced in a fail-closed manner at the execution boundary—thereby confining non-deterministic agent reasoning while maintaining deterministic accountability.
>
> We evaluate DDM in the domain of agentic commerce, where intent-execution misalignment manifests as direct financial loss. Experiments across multiple LLMs show that unconstrained agents violate user-specified constraints in a significant fraction of complex transactions. A DDM-based execution control prototype substantially reduces these violations while maintaining low latency overhead, and enables post-hoc reproduction of every authorization decision from audit logs alone. Our results suggest that deterministic delegation at the execution boundary is a necessary and currently missing architectural layer for trustworthy autonomous agent systems.

（約230語。実験結果は暫定表現。Paper deadline前に数値で更新。）

---

## 10. スケジュール

### Phase 0：Abstract登録（〜2/20 AoE）⚡ 最優先

| 日付 | タスク |
|---|---|
| **2/18（今日）** | HotCRPアカウント作成、Abstractドラフト確定 |
| **2/19** | Abstract最終レビュー・登録 |
| **2/20 AoE** | ⏰ Abstract Registration Deadline |

### Phase 1：実験＋執筆 並行（2/19〜2/26）

| 日付 | 実験 | 執筆 |
|---|---|---|
| 2/19–20 | 環境構築（Mock API, Agent, DDMプロトタイプ） | Sec 1–2（Intro, Problem） |
| 2/21–22 | 実験1（ベースライン）実行 | Sec 3（Related Work） |
| 2/23 | 実験2（DDM制御）実行 | Sec 4（DDM形式定義） |
| 2/24 | 結果整理・分析 | Sec 5（Architecture） |
| 2/25 | 追加実験（必要なら） | Sec 6（Evaluation） |
| 2/26 | — | Sec 7–8、全体推敲、匿名化 |
| **2/27 AoE** | | ⏰ Paper Submission Deadline |

### フォーマット準備

- ACM `sigconf` テンプレート：`\documentclass[sigconf,anonymous]{acmart}`
- ダブルブラインド：著者名・所属・Acknowledgments削除
- PDFメタデータの匿名化確認

---

## 11. 成功の定義

今回の成功とは：

1. **DDMという概念が新規性として認識される**こと
2. **実行レイヤーの決定論的委任**という軸が査読者に明確に伝わること
3. **Trust Gapという問題名が引用可能な形で確立される**こと
4. **AEGの土台となる、引用可能な第一の礎石**が成立すること

AEGの領域宣言は次段階で行う。

---

## 12. スタンスの確認

今回は「領域を取る宣言」ではない。

**領域を取るための第一の礎石を打つ。**

- DDMに集中する
- 広げない
- 焦らない
- 構成を途中で変えない

---

## 付録A：タイトル候補

**第一候補（推奨）：**
> Deterministic Delegation Model for Autonomous Agent Execution

**理由：** 学術概念として引用可能。「Deterministic」「Delegation」「Autonomous Agent」がキーワードとしてCFPの複数ピラーに刺さる。

**代替候補：**
- "DDM: Bridging the Trust Gap Between Policy Decision and Agent Execution"
- "Fail-Closed Delegation: A Deterministic Model for Accountable Agent Execution"
- "The Trust Gap in Agentic Systems: A Deterministic Delegation Approach"

---

## 付録B：両プランからの採用判断ログ

| 論点 | 第一プラン（Claude案） | Point 0案 | 統合版での採用 |
|---|---|---|---|
| 中心概念の名前 | TrustKit（プロダクト名） | DDM（学術概念名） | **DDM** — 引用可能性を優先 |
| 問題の名前 | Trust Gap | （明示なし） | **Trust Gap** — 問題にも名前を付ける |
| 将来領域の名前 | （なし） | AEG | **AEG** — 射程の示唆としてのみ |
| スコープ | 5コンポーネント全提示 | DDMに集中 | **DDM集中** — 9ページで散漫にしない |
| Related Work位置 | Section 3 | Section 7 | **Section 3** — 早期に差別化を確信させる |
| 実験本数 | 3本 | 最小限 | **2本** — ベースライン＋DDM制御の対比 |
| 形式モデル | 薄い | M = f(u, cap, r, ctx, p_v) | **Point 0の定義を深化** |
| Abstractドラフト | TrustKit中心 | （なし） | **DDM中心で新規作成** |
| 実験指標 | 詳細に定義済み | （未定義） | **第一プランの指標体系を採用** |
| スケジュール | 9日間詳細 | （未定義） | **第一プランのスケジュールを採用・調整** |
