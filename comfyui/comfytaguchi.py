import json, time, uuid, requests
from pathlib import Path

COMFYUI_URL = "http://127.0.0.1:8188"
WORKFLOW_FILE = "workflow_api.json"

# Fill these in once you share the workflow JSON:
# key = variable name, value = (node_id, input_key)
VAR_NODES = {
  "A": ("???", "text"),
  "B": ("???", "text"),
  "C": ("???", "text"),
  "D": ("???", "text"),
}

L9 = [
  (0.6, 46, 3, 0.70),
  (0.6, 53, 5, 0.85),
  (0.6, 60, 7, 1.00),
  (0.8, 46, 5, 1.00),
  (0.8, 53, 7, 0.70),
  (0.8, 60, 3, 0.85),
  (1.0, 46, 7, 0.85),
  (1.0, 53, 3, 1.00),
  (1.0, 60, 5, 0.70),
]

def queue_prompt(workflow, client_id):
  r = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow, "client_id": client_id})
  r.raise_for_status()
  return r.json()["prompt_id"]

def wait_for_completion(prompt_id, poll_interval=5.0):
  while True:
      r = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
      if prompt_id in r.json():
          return
      time.sleep(poll_interval)

def main():
  base_workflow = json.loads(Path(WORKFLOW_FILE).read_text())
  client_id = str(uuid.uuid4())

  for i, (a, b, c, d) in enumerate(L9, 1):
      print(f"Run {i}/9 — A={a}  B={b}  C={c}  D={d}")
      wf = json.loads(json.dumps(base_workflow))  # deep copy

      for var, val in zip("ABCD", (a, b, c, d)):
          node_id, input_key = VAR_NODES[var]
          wf[node_id]["inputs"][input_key] = str(val)

      prompt_id = queue_prompt(wf, client_id)
      print(f"  queued {prompt_id}, waiting...")
      wait_for_completion(prompt_id)
      print(f"  done.")

  print("All 9 runs complete.")

if __name__ == "__main__":
  main()