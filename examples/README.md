# cfn-handler examples

Working SAM-deployable Custom Resource handlers.

Each example is a standalone SAM project; deploy with:

```sh
cd <example-dir>
sam build
sam deploy --guided
```

| Example | What it shows |
|---|---|
| [basic](basic/) | Synchronous Create / Update / Delete with response data. |
| [polled](polled/) | Long-running Create using `poll_create`; library provisions a CloudWatch Events re-invocation. |
| [with-physical-id](with-physical-id/) | Explicit `physical_resource_id` control (meaningful id on Create, replacement on Update). |
| [failing](failing/) | Handler that raises — demonstrates the FAILED-response path that lets CloudFormation roll back cleanly. |

## Notes

- All examples use Python 3.12 on `arm64`. Adjust `Runtime` and
  `Architectures` to your needs.
- The `polled` example needs IAM permissions to manage CloudWatch Events
  rules and Lambda permissions on its own function. The other examples
  need no extra permissions.
- Every example imports `cfn_handler` at module load, so make sure your
  Lambda packaging includes the `cfn-handler` wheel (`pip install
  cfn-handler -t .` inside `src/`, or use SAM's `BuildMethod: python3.12`
  with a `requirements.txt`).
