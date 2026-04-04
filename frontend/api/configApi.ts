export async function switchConfig(payload: any) {
  const res = await fetch("http://127.0.0.1:8000/system/config/switch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })

  if (!res.ok) throw new Error("Switch failed")

  return res.json()
}
