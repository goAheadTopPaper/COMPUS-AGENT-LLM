# 全校课程与 subjectId 对照

2026-11-23 已从理大 [eStudent 公开课程查询页面](https://estudent.polyu.edu.hk/e-public/subject-search/) 验证按课程查询不要求 programmeId。官方页面同时提供 Search by Subject 和 Search by Programme。

## 实测接口

按课程代码查询：

```http
POST https://estudent.polyu.edu.hk/proxy/e-public/srs-api/student-portal/public/subjects/search
Content-Type: application/json

{"acadYearSem":"20261","subjCode":"AF5640"}
```

响应 `value[].id` 即 subjectId，`subjCode` 为课程代码，`subjectTitles["UI_LANGUAGE||EN"]` 为英文名称。这个请求不含 programmeId。

随后查询课表：

```http
POST https://estudent.polyu.edu.hk/proxy/e-public/srs-api/student-portal/public/subject-component-quota-groups/search/batch
Content-Type: application/json

{"queries":[{"acadYear":"2026","acadSemester":"1","subjectId":41243}]}
```

AF5640 / METAVERSE ECONOMICS AND ECOSYSTEMS 的 ID 为 41243；COMP5517 / HUMAN COMPUTER INTERACTION 的 ID 为 7884。

## 全校清单覆盖

先调用 `/public/system/dropdown-options/public?yearSem=20261`，读取 `value.subjectOfferingDepartments` 的全部 45 个部门；分别以 `{"acadYearSem":"20261","orgUnitId":部门ID}` 查询，再按 subjectId 去重。

本次取得 2546 个不同 subjectId、2546 个不同课程代码，无失败请求，每个部门均少于 1000 条。涵盖的是该学期公开下拉框及接口可见的课程，不代表所有历史、未来或非公开课程。

- `subjects.discovered.json`：完整清单及学期、来源、采集时间。
- `subjects.discovered.csv`：便于查看的课程代码、名称、ID 对照表。
- `subjects.discovered.report.json`：各部门数量与覆盖检查。
- 原始响应：`.local/subject_discovery/20261/`（不入 Git）。

刷新指定学期：

```powershell
python -X utf8 -B scripts/fetch_subjects.py --year-sem 20261
```

## 直接查询方式

前端左侧点击“清空项目和查询记录”，项目栏留空，然后直接问：

> 明天元宇宙经济课几点、在哪个教室上课？

也可直接输入课程代码。已有项目筛选仍然保留，不填写时默认全校范围；项目映射文件不是全校课程查询的必需配置。

程序的大学范围查询：

1. 明确课程代码：直接调用实时课程接口，取得 ID。
2. 名称/中文简称：使用同学期全校清单；如不存在，则通过实时英文关键词检索。
3. 清单较大时，先生成检索词、按标题筛出每个查询最多 40 个候选，再让模型识别课程。模型只能选择候选里的 ID。
4. 从快照找到的课程会实时核对 ID，再查询课表、按教学周筛选，交给 Answerer 和 Verifier。
5. 多门同名课程、同一缩写对应多门课或版本变化时，追问课程代码，不猜测用户项目；公开课表不代表个人已注册该课程。

课程歧义现在提供可点击的实际候选。以 HCI 为例，可选 COMP3423 或 COMP5517；选中后保留原问题与日期直接继续，或在结果下的“补充信息”框输入课程代码后继续。规划器不再因缩写提前拦截，而是先让 Schedule 查询真实候选。
