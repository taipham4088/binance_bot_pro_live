type SwitchConfigPayload = {
  session_id: string
  engine?: string
  engine_profile?: string
  position_mode?: string
  symbol?: string
  mode?: string
}

export async function switchConfig(payload: SwitchConfigPayload) {
  const res = await fetch(
    "http://127.0.0.1:8000/system/config/switch",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  )

  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || "Failed to switch config")
  }

  return await res.json()
}
