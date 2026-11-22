# eStudent 项目名称与内部 ID 对照

2026-11-23 从理大公开课程查询页面的客户端脚本定位并实际调用以下公开接口，无需登录。

来源页面：https://estudent.polyu.edu.hk/e-public/subject-search/listing?mode=subject

## 接口

获取当学期项目开办部门：

```http
GET https://estudent.polyu.edu.hk/proxy/e-public/srs-api/student-portal/public/system/dropdown-options/public?yearSem=20261
```

返回 `value.programmeHostingDepartments`，每条 `label` 为部门名称，`value` 为部门 ID。

按部门查询项目：

```http
POST https://estudent.polyu.edu.hk/proxy/e-public/srs-api/student-portal/public/programmes/search
Content-Type: application/json

{"yearSem":"20261","orgUnitId":48}
```

`48` 是本次返回的 Computing 部门 ID。返回的 `value` 是项目列表：

- `id`：可用于课程接口的 programmeId。
- `progCode`：公开项目代码。
- `subCode`：项目分支代码，可能为空格，导出时已去掉首尾空白。
- `programmeTitles`：标题列表；`mdmTitleTypeTk=MDM_TITLE_TYPE||PROG_TITLE` 为项目名称，`uiLanguageTk` 区分语言。
- `progModeTk`、`implYear`、`lastAdmYear`：模式、实施年份、最后招生年份等元数据；模式原始值保留，未擅自解释。

不按部门的请求返回恰好 1000 条，可能有数量限制。此次按公开下拉框的全部 44 个部门分别查询并按内部 id 去重，得到 3715 条记录、683 个不同公开项目代码。所有部门均成功返回，每个部门均少于 1000 条。此覆盖判断只针对该公开下拉框暴露的部门，并不证明覆盖学校所有历史项目、附属机构或未来开办安排。

接口即使传入 yearSem，也会返回旧版本和未来版本，不能视为当期正在招生的项目表。此次有 132 条记录的 implYear 大于 2026。不要仅按名称挑第一条 ID。

## 导出文件

- `programmes.discovered.json`：兼容 ProgrammeResolver 的映射格式，保留双语原始名称别名、公开代码、分支、模式、实施年份、部门及来源。name 带代码/模式/实施年份，以便展示同名候选。
- `programmes.discovered.csv`：便于查看的名称与 ID 表。
- `programmes.discovered.report.json`：各部门条数、失败情况和覆盖限制。

示例：61038 / MSc METAVERSE TECHNOLOGY 的 2023 实施版本 ID 为 9134；61037-FAI / MSc ARTIFICIAL INTELLIGENCE & BIG DATA COMPUTING 的 ID 为 8676，61037-PAI 为 8677。

默认 `programmes.json` 未替换。使用这份清单可配置 `PROGRAMME_MAP_PATH=programmes.discovered.json`。Resolver 已支持简繁、称谓后缀、科技/技术及模糊名称匹配，并按查询学年排除未来实施和已结束运行的版本。例如 2026 学年中，“元宇宙科技项目”“元宇宙技术项目”“元宇宙科技理學碩士”都会命中 9134，而不是 2027 年的新版本。多个版本仍适用时会进一步追问项目代码、分支或入学年份，不直接选第一条。

重新抓取：

```powershell
python -X utf8 -B scripts/fetch_programmes.py --year-sem 20261
```

脚本只写发现清单和报告，不覆盖默认映射。原始响应保存在忽略提交的 `.local/programme_discovery/20261/`。
