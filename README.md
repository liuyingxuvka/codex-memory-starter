# Codex-Memory-Plugin

Current template version: `v0.1.6`

中文 / Chinese first. A full one-to-one English version is below.

一个**不是把“记忆”写成零散规则，而是把经验写成可检索、可审查、可版本化预测模型**的本地系统。

它和很多“记忆功能”最大的差别，不是“能不能记住一条东西”，而是**记住的对象是什么**：

- 不是只记一条“应该怎么做”的规则。
- 而是记一个更像模型的关系：
  如果在某种条件下这样做，更可能发生什么；
  如果换一种做法，又更可能发生什么。
- 这意味着一条记忆可以不只是单结论，还可以有分支、备选结果、对比路径。

换句话说，这个项目的核心不是“存规则”，而是**建模**。

## 入口 / Start here

如果你是普通使用者：

- 你要找的是一个**本地、文件型、可建模用户与系统自身行为**的记忆框架
- 先看下面的“为什么这和普通记忆不一样”
- 然后直接跳到“快速开始”

如果你是开发者：

- 先读 `PROJECT_SPEC.md`
- 再看 `.agents/skills/local-kb-retrieve/`
- 最后看 `local_kb/` 和 `tests/`

## 为什么这和普通记忆不一样

- **它记录的是预测，不只是建议。**
  一条卡片不是“以后应该这样”，而是“在这个场景里，这个动作更可能带来这个结果”。
- **它允许 alternatives。**
  也就是说，不只是“正确答案”，还可以明确保留“如果走另一条路径，会更可能变差到哪里”。
- **它会对用户建模。**
  不是抽象的人格标签，而是“这个用户在什么任务里，更可能偏好什么结构、讨厌什么遗漏、如何判断结果是否清晰”。
- **它也会对自己建模。**
  也就是对 Codex / runtime 本身的行为建模：在什么提示、流程、工具条件下，更可能犯什么错，修正后又会改善什么。
- **它是文件型、可审查、可版本化的。**
  你可以在 Git 里看到每条结构化经验如何被记录、修改、对比、发布。

## 这套系统实际在建模什么

这里至少有三类模型：

1. **任务模型**
   例如：面对某类仓库发布、调试、汇报任务时，什么做法更可能成功。
2. **用户模型**
   例如：某个用户在 GitHub README 上更可能希望先看到版本号、用户入口、中文优先结构，而不是先看开发者说明。
3. **自我 / 运行时模型**
   例如：当 KB postflight 只是隐含要求时，Codex 更可能漏掉经验回写；当它被显式纳入 done 条件时，回写更稳定。

这也是这个项目很有吸引力的地方：
它不是只说“我记住了一条偏好”，而是把**用户怎么反应**、**系统自己怎么犯错**、**改完之后为什么更好**，都放进同一个建模框架里。

## 一个最小例子

下面这个例子不是“规则清单”，而是一条真正带分支的模型：

```yaml
id: pref-release-presentation
type: preference
scope: private
domain_path:
  - repository
  - github-publishing
  - readme-presentation
if:
  notes: When preparing a public GitHub page for this user.
action:
  description: Hide version visibility and place developer setup before the user entry.
predict:
  expected_result: Review friction is more likely and the page is less likely to feel clear.
  alternatives:
    - when: If version is visible and the user entry appears early
      result: The page is easier for this user to scan and approve.
use:
  guidance: Keep version visible, surface the user entry early, and preserve the chosen bilingual structure.
```

重点不是 YAML 本身，而是这条结构表达的是：

- 条件是什么
- 动作是什么
- 结果更可能怎样
- 换一种做法时又会怎样

这就是“模型”，而不是单条规则。

## 这也是为什么它能处理“修正”而不只是“结论”

很多系统最后只会留下一个成功结论。

这个仓库现在开始更强调**对比证据**（contrastive evidence）：

- 原来走了一条较弱路径，结果更差
- 后来改成另一条路径，结果更好
- 两边都被保留下来

这样未来的卡片不只会说“推荐这样做”，还可以明确说：

- 如果重复旧路径，更可能发生什么坏结果
- 如果采用修正路径，更可能得到什么改善

这让记忆从“静态建议”更接近“可操作模型”。

## 它不只会“睡眠”，也会“做梦”

这个仓库现在把维护生命周期明确拆成两条不同的自动化机制：

- **Sleep / 睡眠**
  处理已经发生过的真实任务证据。
  它负责整理 observation history、生成或审查 candidate、检查 taxonomy gap、以及做低风险 maintenance。
- **Dream / 做梦**
  处理“还没真正做过很多次，但值得验证”的邻近机会。
  它会从 miss、weak hit、taxonomy gap、低置信 candidate 或 proposal-only action 中挑一个小问题，做一次有边界的本地验证，然后只把结果写回 history 或 candidate。

这两条机制不会混在一起：

- `KB Sleep` 每天 12:00 运行
- `KB Dream` 每天 13:00 运行
- 它们由安装器自动写入 `$CODEX_HOME/automations/`
- 重新在另一台机器上运行安装器时，这两条节律会一起被恢复

换句话说，这个项目现在不只是“整理记忆”，还开始支持一种受控的“做梦式探索”：
先在小范围内试探值得学的新路径，再把验证过的结果作为候选经验写回系统。

## 快速开始

先安装：

```bash
python scripts/install_codex_kb.py --json
python scripts/install_codex_kb.py --check --json
```

安装器除了全局 preflight skill 之外，也会在 `$CODEX_HOME/automations/` 下刷新这个仓库的两条 repo-managed 定时维护规则：

- `KB Sleep`: 每天 12:00 运行 sleep maintenance
- `KB Dream`: 每天 13:00 运行 bounded dream exploration

这样把仓库换到另一台机器后，重新跑一次安装器，就会把同样的维护节律一起带过去。

做一次检索：

```bash
python .agents/skills/local-kb-retrieve/scripts/kb_search.py \
  --path-hint "repository/github-publishing/readme-presentation" \
  --query "prepare a public GitHub page for this user" \
  --top-k 5
```

## 这个公开仓库里放什么，不放什么

这个仓库公开发布的是：

- 工作流
- schema
- skills
- 检索、记录、maintenance 工具
- 安全可公开的示例结构

默认**不应该**顺手把这些真实运行内容一起公开：

- 你的 live private cards
- 你的真实 `kb/history`
- 你的真实 `kb/candidates`
- 任何用户特定、敏感、未确认可公开的经验

## Repository layout

```text
.
├─ AGENTS.md
├─ PROJECT_SPEC.md
├─ README.md
├─ VERSION
├─ docs/
├─ .agents/
├─ kb/
├─ local_kb/
├─ schemas/
├─ scripts/
├─ templates/
└─ tests/
```

## English Version

A local system that treats experience not as scattered “memory rules,” but as **retrievable, reviewable, versioned predictive models**.

The biggest difference between this project and many other “memory features” is not whether it can remember one item. The difference is **what kind of thing it remembers**:

- It does not only remember a rule such as “you should do X.”
- It remembers something closer to a model:
  if you act this way under certain conditions, what becomes more likely;
  if you choose another path instead, what becomes more likely then.
- That means one memory can contain not just a single conclusion, but also branches, alternatives, and contrastive paths.

In other words, the core of this project is not “storing rules.” It is **modeling**.

### Start here

If you are a normal user:

- What you are looking at is a **local, file-based memory framework that can model both the user and the system itself**
- First read “Why this is different from ordinary memory”
- Then jump directly to “Quick start”

If you are a developer:

- Read `PROJECT_SPEC.md` first
- Then look at `.agents/skills/local-kb-retrieve/`
- Then look at `local_kb/` and `tests/`

### Why this is different from ordinary memory

- **It stores predictions, not only advice.**
  A card is not just “do this next time.” It is “in this scenario, this action is more likely to lead to this result.”
- **It allows alternatives.**
  That means it does not keep only one “correct answer.” It can also preserve what is more likely to go wrong if another path is taken.
- **It models the user.**
  Not as abstract personality labels, but as concrete task-conditioned patterns such as what structure this user is more likely to prefer, what kinds of omissions they dislike, and how they judge whether an outcome is clear.
- **It also models itself.**
  That means modeling Codex / runtime behavior itself: under which prompts, workflows, or tool conditions it is more likely to make certain mistakes, and how the outcome changes after the path is corrected.
- **It is file-based, inspectable, and versionable.**
  You can see in Git how each structured lesson is recorded, revised, compared, and published.

### What this system is actually modeling

There are at least three kinds of models here:

1. **Task models**
   For example: when facing a certain kind of repository release, debugging, or reporting task, which approach is more likely to succeed.
2. **User models**
   For example: for a certain user, a GitHub README is more likely to be preferred when the version, user entry, and Chinese-first structure appear early, rather than developer setup appearing first.
3. **Self / runtime models**
   For example: when KB postflight is only an implicit requirement, Codex is more likely to forget the write-back; when it is made an explicit done condition, the write-back becomes more reliable.

This is also one of the most attractive parts of the project:
it does not only say “I remembered one preference.” It places **how the user reacts**, **how the system itself makes mistakes**, and **why the revised path is better** inside the same modeling framework.

### A minimal example

The example below is not a “rule checklist.” It is an actual model with a branch:

```yaml
id: pref-release-presentation
type: preference
scope: private
domain_path:
  - repository
  - github-publishing
  - readme-presentation
if:
  notes: When preparing a public GitHub page for this user.
action:
  description: Hide version visibility and place developer setup before the user entry.
predict:
  expected_result: Review friction is more likely and the page is less likely to feel clear.
  alternatives:
    - when: If version is visible and the user entry appears early
      result: The page is easier for this user to scan and approve.
use:
  guidance: Keep version visible, surface the user entry early, and preserve the chosen bilingual structure.
```

The important point is not the YAML syntax itself. The structure is expressing:

- what the condition is
- what the action is
- what result becomes more likely
- and what happens if a different path is chosen

That is a **model**, not just one rule.

### Why it can capture corrections, not just conclusions

Many systems end up preserving only one successful conclusion.

This repository now puts more emphasis on **contrastive evidence**:

- an earlier weaker path was taken, and the result was worse
- later the path was changed, and the result became better
- both sides are preserved

That means future cards do not only say “this is the recommended path.” They can also say clearly:

- what bad result is more likely if the old path is repeated
- what improvement is more likely if the corrected path is used

This moves memory closer to an **operational model** rather than a static suggestion.

### It Does Not Only “Sleep,” It Also “Dreams”

The repository now separates maintenance into two different recurring lanes:

- **Sleep**
  Works on real task evidence that already happened.
  It consolidates observation history, reviews or creates candidates, inspects taxonomy gaps, and runs the current low-risk maintenance paths.
- **Dream**
  Works on nearby opportunities that have not yet been exercised enough in live work.
  It selects one bounded miss, weak hit, taxonomy gap, low-confidence candidate, or proposal-only action, runs a small local validation pass, and writes back only to history or candidates.

These lanes stay deliberately separate:

- `KB Sleep` runs daily at 12:00
- `KB Dream` runs daily at 13:00
- both are provisioned automatically by the installer under `$CODEX_HOME/automations/`
- rerunning the installer on another machine restores the same cadence

So the project is no longer only about consolidating memory. It now also supports a controlled dream-style exploration loop:
probe adjacent possibilities in a bounded way first, then write validated results back as provisional experience.

### Quick start

Install first:

```bash
python scripts/install_codex_kb.py --json
python scripts/install_codex_kb.py --check --json
```

The installer refreshes not only the global preflight skill but also the repository-managed cron automations in `$CODEX_HOME/automations/`:

- `KB Sleep`: daily 12:00 sleep maintenance
- `KB Dream`: daily 13:00 bounded dream exploration

That means re-running the installer on another machine carries over the same maintenance cadence together with the repository root configuration.

Run one retrieval:

```bash
python .agents/skills/local-kb-retrieve/scripts/kb_search.py \
  --path-hint "repository/github-publishing/readme-presentation" \
  --query "prepare a public GitHub page for this user" \
  --top-k 5
```

### What this public repository includes, and what it does not

This public repository is meant to publish:

- workflows
- schemas
- skills
- retrieval, recording, and maintenance tools
- safe public example structures

By default, it **should not** casually publish these real runtime contents together with it:

- your live private cards
- your real `kb/history`
- your real `kb/candidates`
- any user-specific, sensitive, or not-yet-confirmed-public lessons

### Repository layout

```text
.
├─ AGENTS.md
├─ PROJECT_SPEC.md
├─ README.md
├─ VERSION
├─ docs/
├─ .agents/
├─ kb/
├─ local_kb/
├─ schemas/
├─ scripts/
├─ templates/
└─ tests/
```
