# cfn-handler — Lambda Layer

`cfn-handler` is published as a public AWS Lambda Layer in every release
across ~17 commercial regions. Reference the layer in your Lambda function
to use `cfn-handler` without bundling it into your function package.

[![Lambda Layer](https://img.shields.io/github/v/release/igorlg/cfn-handler?label=lambda%20layer&color=ff9900&logo=amazonaws)](https://github.com/igorlg/cfn-handler/releases/latest)

## Why use the layer?

- **No vendoring** — your function package stays small (~20 KB lighter).
- **No build step** — skip `pip install -t ./` during deploy.
- **Same code as PyPI** — the layer is the wheel, repackaged for Lambda.

## ARN format

```
arn:aws:lambda:<region>:<account-id>:layer:cfn-handler:<version>
```

The maintainer's account ID and the version number for a specific release
appear in the inventory surfaces below.

## Find an ARN

### Option 1: GitHub Release page (browser)

Visit `https://github.com/igorlg/cfn-handler/releases/latest` (or any
specific release). Each release's notes include a per-region ARN markdown
table.

### Option 2: Programmatic JSON manifest

Every release uploads a `layer-arns.json` asset to the GitHub Release.
Fetch the latest:

```bash
curl -fsSL https://github.com/igorlg/cfn-handler/releases/latest/download/layer-arns.json
```

Pin a specific version:

```bash
curl -fsSL https://github.com/igorlg/cfn-handler/releases/download/v1.2.0/layer-arns.json
```

Schema:

```json
{
  "version": "1.2.0",
  "layer_name": "cfn-handler",
  "regions": {
    "us-east-1": "arn:aws:lambda:us-east-1:<account-id>:layer:cfn-handler:N",
    "us-east-2": "arn:aws:lambda:us-east-2:<account-id>:layer:cfn-handler:N",
    "...": "..."
  }
}
```

### Option 3: AWS CLI direct query

If you know the layer name (`cfn-handler`) and the maintainer's account ID,
list versions in your region:

```bash
aws lambda list-layer-versions \
  --layer-name arn:aws:lambda:us-east-1:<account-id>:layer:cfn-handler \
  --region us-east-1
```

This works **only** because the layer has a public read grant (anyone in
any AWS account can `GetLayerVersion`/`ListLayerVersions`).

## Use in SAM

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  MyCustomResourceFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: python3.12
      Handler: index.handler
      CodeUri: src/
      Layers:
        - arn:aws:lambda:us-east-1:<account-id>:layer:cfn-handler:1
```

In your handler:

```python
from cfn_handler import CustomResource

resource = CustomResource()

@resource.create
def on_create(event, context):
    return {"Endpoint": "..."}

@resource.update
def on_update(event, context):
    return {"Endpoint": "..."}

@resource.delete
def on_delete(event, context):
    return None

def handler(event, context):
    return resource(event, context)
```

## Use in CDK (Python)

```python
from aws_cdk import aws_lambda as lambda_, Stack

class MyStack(Stack):
    def __init__(self, scope, id, **kwargs):
        super().__init__(scope, id, **kwargs)

        cfn_handler_layer = lambda_.LayerVersion.from_layer_version_arn(
            self, "CfnHandlerLayer",
            f"arn:aws:lambda:{self.region}:<account-id>:layer:cfn-handler:1",
        )

        lambda_.Function(
            self, "MyFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_asset("src"),
            layers=[cfn_handler_layer],
        )
```

## Use in CDK (TypeScript)

```ts
import { Stack, StackProps } from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { Construct } from "constructs";

export class MyStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const cfnHandlerLayer = lambda.LayerVersion.fromLayerVersionArn(
      this, "CfnHandlerLayer",
      `arn:aws:lambda:${this.region}:<account-id>:layer:cfn-handler:1`,
    );

    new lambda.Function(this, "MyFunction", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "index.handler",
      code: lambda.Code.fromAsset("src"),
      layers: [cfnHandlerLayer],
    });
  }
}
```

## Compatibility

| | Supported |
|---|---|
| Lambda runtimes | `python3.10`, `python3.11`, `python3.12`, `python3.13`, `python3.14` |
| Lambda architectures | `x86_64`, `arm64` |
| Regions | See [`regions.txt`](regions.txt) |
| GovCloud (`us-gov-*`) | Not supported (out of scope for now) |
| China (`cn-*`) | Not supported (out of scope for now) |

## Don't want to use the layer?

`pip install cfn-handler` from PyPI continues to work. The layer is an
alternative; the wheel is the canonical artifact.

If you want to deploy the layer **in your own AWS account** (e.g. for
GovCloud, China, an offline environment, or just personal preference),
download the ZIP from any GitHub Release:

```bash
curl -fsSL https://github.com/igorlg/cfn-handler/releases/latest/download/cfn_handler-1.2.0-layer.zip -o layer.zip
aws lambda publish-layer-version \
  --layer-name cfn-handler \
  --zip-file fileb://layer.zip \
  --compatible-runtimes python3.10 python3.11 python3.12 python3.13 python3.14 \
  --compatible-architectures x86_64 arm64 \
  --region <your-region>
```

The wheel contents are identical to the public layer's contents.

## See also

- [Library README](../README.md) for the full `cfn-handler` API.
- [MAINTAINER.md](MAINTAINER.md) for publishing operations (maintainer-only).
- [docs/CI.md](../docs/CI.md) for the broader release pipeline.
