# 检索层评测结果

- 查询数：24（可答 20 / 可拒答 3 / 需 Verifier 1）
- **证据命中率 Recall@5**：19/20 = **95.0%**
- **正确拒答率**（年份/编号不存在时返回空）：3/3 = **100.0%**
- 中位延迟：6 ms（本地 BM25，无网络）

| ID | 类别 | 查询 | 期望 | 返回证据 | 结果 |
|---|---|---|---|---:|---|
| R01 | policy | How do I request leave of absence for a few days in 2026/2 | 可答 | 5 | PASS |
| R02 | policy | Can I pause my studies for a semester in 2026/27? | 可答 | 5 | FAIL |
| R03 | policy | When will I be put on academic probation in 2025/26? | 可答 | 5 | PASS |
| R04 | policy | How long do I have to appeal my assessment results in 2026 | 可答 | 5 | PASS |
| R05 | policy | What should I do if illness prevents me from attending an  | 可答 | 5 | PASS |
| R06 | policy | In 2026/27, can I retake a subject I have already passed t | 可答 | 5 | PASS |
| R07 | policy | How do I apply for credit transfer in 2026/27? | 可答 | 5 | PASS |
| R08 | policy | What happens if I do not pay tuition fees on time in 2026/ | 可答 | 5 | PASS |
| R09 | policy | If I stop attending one module after add/drop in 2025/26,  | 可答 | 1 | PASS |
| R10 | policy | What counts as plagiarism in 2026/27? | 可答 | 5 | PASS |
| R11 | policy | What is the maximum study load per semester? | 可答 | 5 | PASS |
| R12 | programme | How many credits are required for JUPAS JS3060 for Septemb | 可答 | 4 | PASS |
| R13 | programme | What are the graduation credit requirements for programme  | 可答 | 1 | PASS |
| R14 | programme | How much is tuition for Metaverse Technology January 2027  | 可答 | 1 | PASS |
| R15 | subject | What are the credit value and prerequisites for COMP5926? | 可答 | 1 | PASS |
| R16 | subject | What is the credit value of COMP5584? | 可答 | 1 | PASS |
| R17 | service | Where is the IT HelpCentre and how can I contact it? | 可答 | 5 | PASS |
| R18 | service | How many library books may a taught postgraduate student b | 可答 | 5 | PASS |
| R19 | service | Can part-time students use UHS? | 可答 | 4 | PASS |
| R20 | service | How do I book an appointment for counselling? | 可答 | 5 | PASS |
| U01 | unanswerable | What are the subject withdrawal rules in 2020/21? | 不可答 | 0 | PASS |
| U02 | unanswerable | What are the graduation credits for programme 99999 in 202 | 不可答 | 0 | PASS |
| U03 | unanswerable | What is the prerequisite of COMP5926 in 2020/21? | 不可答 | 0 | PASS |
| U04 | unanswerable | What grade will the COMP5584 lecturer give this semester? | 需校验 | 4 | PASS |

> 说明：本表只测检索层与拒答，不评价生成答案的事实正确性；BM25 词频基线，未启用神经向量；中文查询不在本表范围内（见 limitation）。
> 语义型无解题（如预测给分）检索仍会返回相邻证据，拒答须由 Verifier 判定，不计入上表拒答率。
