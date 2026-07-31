# Evaluation Scenarios

`collections-scenarios.json` is the full capstone behavior suite. It covers:

- payment risk with a broken promise;
- portfolio prioritization;
- open-dispute handling;
- active promise-to-pay handling;
- context-aware drafting; and
- approval-boundary prompt injection.

The authoritative executable suite uses ADK's native evalset format:

```bash
python scripts/seed_data.py
adk eval agents \
  tests/eval/collections.evalset.json \
  --config_file_path tests/eval/adk_eval_config.json \
  --print_detailed_results
```

`collections-scenarios.json`, `basic-dataset.json`, and `eval_config.yaml`
mirror the agents-cli inference/grading format for managed evaluation
workflows. ADK native evaluation is used locally because it executes ADK
`McpToolset` objects directly.
