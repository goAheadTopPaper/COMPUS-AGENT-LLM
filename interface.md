# 查询课程接口文档

### 拉取项目下的课程列表：
https://estudent.polyu.edu.hk/proxy/e-public/srs-api/student-portal/public/subjects/search

POST方法

参数示例：{
    acadYearSem: "20261", // 26年9月之后就是2026，后面数字代表学期，9-次年1月是1，次年2月-7月是2，次年7月-次年9月是3，次年9月之后就变成2027重新从1开始
    programmeId: 9134, // 项目id
}

返回结果：{
    id：课程id，
}

### 拉取课程的安排：
https://estudent.polyu.edu.hk/proxy/e-public/srs-api/student-portal/public/subject-component-quota-groups/search/batch

POST方法

参数示例：{
    queries： {
        acadSemester: "1", // 2数字代表学期，9-次年1月是1，次年2月-7月是2，次年7月-次年9月是3，次年9月之后重新从1开始
        acadYear: "2026", // 26年9月之后就是2026，次年9月之后就变成2027
        subjectId: 41243, // 课程id
    }
}

返回结果：{
    quotaGroupCode: 分组信息 // 可能有很多分组，分组里面的课程安排都是一样的，取一个分组就行了
    deliveryTimeFrom： 课程开始时间
    deliveryTimeTo： 课程结束时间
    acadWeekFm：当前信息的适用周数开始 // 从当前学期月份开始到现在算周数，取适用周数的数据
    acadWeekTo：当前信息的适用周数结束 // 从当前学期月份开始到现在算周数，取适用周数的数据
    roomCodeList：教室列表
    cttDayOfWeekTk: 星期几上课
    subjectCode: 课程code
}

