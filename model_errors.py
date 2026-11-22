"""Display-safe model failures: never include provider bodies or credentials."""


class ModelRequestError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        hint = {400: "请求参数无效，请检查模型及 JSON 输出支持。",
                401: "模型服务鉴权失败，请检查本地 LLM_API_KEY。",
                402: "模型服务余额不足，请检查服务商账户。",
                403: "模型服务拒绝访问，请检查账户或网络权限。",
                404: "模型接口或模型不存在，请检查完整 LLM_ENDPOINT 和模型名称。",
                405: "该地址不接受聊天请求，请检查完整 LLM_ENDPOINT。",
                422: "模型服务无法处理请求参数，请检查接口兼容性。",
                429: "模型服务限流，请稍后重试。"}.get(status_code,
                    "模型服务暂时不可用，请检查服务商状态。" if status_code >= 500
                    else "模型服务请求失败，请检查接口配置。")
        super().__init__(f"HTTP {status_code}：{hint}")
