import os
import httpx

async def generate_ai_advice(summary: dict, review: dict):
    api_key = os.getenv("AI_API_KEY", "").strip()
    if not api_key:
        return fallback(summary, review)
    base = os.getenv("AI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("AI_MODEL", "gpt-4o-mini")
    prompt = f"""你是大学生运动训练助手。请根据以下数据给出简短、可执行的建议，中文输出，包含：近7天总结、下周计划、注意事项。\n数据：{summary}\n阶段复盘：{review}"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.4},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return fallback(summary, review) + "\n\n（AI 接口调用失败，已自动使用系统规则建议。）"

def fallback(summary, review):
    if summary["avg_intensity"] >= 4.5:
        intensity = "近期强度偏高，下周至少安排 1–2 天主动恢复或轻量活动。"
    else:
        intensity = "训练强度整体可控，可在身体状态良好时逐步增加一点时长。"
    return (
        f"近7天累计运动 {review['weekly_minutes']} 分钟，目标完成度约 {review['completion']}%。{review['advice']}\n"
        f"建议：安排 3–5 次运动，每次 30–60 分钟；记录运动后的主观感受，方便阶段复盘。\n"
        f"注意：出现持续疼痛、头晕、胸闷等异常情况时应停止训练并及时就医。{intensity}"
    )
