# FLRA Alexa Skill Solution

This repository contains an **AWS Serverless** solution for delivering **FLRA (Federal Labor Relations Authority)** updates via an **Alexa skill**, leveraging **RSS feeds**, **LLM-powered summarization**, **DynamoDB** for data storage, **Secrets Manager** for secure API key management, and **CodeBuild + CodePipeline** for CI/CD.

---

## Features

1. **Multiple FLRA Feeds**  
   Consolidates decisions, press releases, and other FLRA feeds in one place.  
2. **LLM Summaries**  
   Summarizes complex legal text into concise bullet points, making it more accessible.  
3. **Metadata Tagging**  
   (Optional) Amazon Comprehend to detect entities (e.g., agencies, unions, case numbers).  
4. **User Preferences**  
   Users can configure notification frequency (daily/weekly) and topics of interest (decisions, press releases, etc.).  
5. **Proactive Notifications**  
   Alexa Proactive Events API for hands-free announcements about new FLRA items.  
6. **Rich Responses**  
   APL and AudioPlayer directives supported for devices with screens or audio streaming.  
7. **Custom Metrics**  
   Records usage and intent metrics in Amazon CloudWatch.  
8. **Secure Secrets**  
   Stores external LLM API keys (and Alexa OAuth tokens) in AWS Secrets Manager.  
9. **CI/CD**  
   Automates build and deploy using AWS CodeBuild + CodePipeline.

### Key Components

- **template.yaml**  
  Defines your AWS resources (DynamoDB tables, Lambda functions, IAM roles, etc.) using AWS SAM. Accepts parameters for secrets, skill ID, deployment stage, etc.

- **code/scheduler/app.py**  
  - Fetches **FLRA RSS feeds** on a schedule defined by EventBridge.  
  - Summarizes new feed entries with an LLM (API key retrieved from Secrets Manager).  
  - Uses Amazon Comprehend (optional) for metadata tagging.  
  - Stores results in DynamoDB.  
  - Sends Proactive Notifications to Alexa devices for subscribed users.

- **code/alexaSkill/app.py**  
  - Responds to Alexa intents (e.g., requesting updates, setting preferences).  
  - Can provide **rich APL** or **AudioPlayer** responses for supported devices.  
  - Tracks usage metrics in Amazon CloudWatch.  
  - Allows users to configure and retrieve their preferences (topic, frequency).

- **buildspec.yml**  
  - Tells **AWS CodeBuild** how to **build, package, and deploy** this SAM application.  
  - Reads environment variables (like `S3_BUCKET`, `STACK_NAME`, `LLMApiSecretName`) from the CodeBuild project or pipeline.

---

## Deployment Instructions

There are two primary ways to deploy this solution:

1. **Local SAM CLI** (manual approach)  
2. **AWS CodePipeline + CodeBuild** (fully automated CI/CD)

Below are the steps for **Option B**, using **CodePipeline** + **CodeBuild**. For local/manual deployment, see the instructions in the [AWS SAM Developer Guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html).

---

### Option B: Using CodePipeline + CodeBuild

1. **Set Environment Variables**  
   In your **CodeBuild project** (or in the CodePipeline stage definition), define environment variables to match the placeholders in `buildspec.yml`. Examples:

   - `S3_BUCKET = my-sam-artifacts`  
   - `STACK_NAME = FLRA-Alexa-Stack`  
   - `LLMApiSecretName = MyLLMApiSecret`  
   - `ComprehendEnabled = true`  
   - `AlexaSkillId = amzn1.ask.skill.xxxxxxx`  
   - `DEPLOYMENT_STAGE = dev`

   **Notes**:
   - **S3_BUCKET**: The S3 bucket where SAM will upload your packaged Lambda code.  
   - **STACK_NAME**: The CloudFormation stack name to create or update.  
   - **LLMApiSecretName**: The name of the Secrets Manager secret storing your LLM API credentials.  
   - **ComprehendEnabled**: Toggles usage of Amazon Comprehend (`true` or `false`).  
   - **AlexaSkillId**: The Skill ID from your Alexa Developer Console.  
   - **DEPLOYMENT_STAGE**: The stage name (e.g., `dev`, `staging`, `production`), appended to resource names.

2. **Start Build**  
   - Once your pipeline (or CodeBuild project) triggers, CodeBuild automatically picks up these variables and executes `buildspec.yml`.

3. **SAM Build and Deploy**  
   - During the build, the following steps occur:
     1. **sam build**: Compiles your SAM application, resolving any dependencies.  
     2. **sam package**: Packages code into a `.zip`, uploads it to `S3_BUCKET`, and generates a CloudFormation template (`out.yaml`).  
     3. **sam deploy**: Deploys the CloudFormation stack to AWS, using the parameter overrides from your environment variables.

4. **Verify Stack**  
   - After deployment, open the **CloudFormation console**. Look for a stack named `FLRA-Alexa-Stack` (or your chosen `STACK_NAME`).  
   - Check the **Outputs** for:
     - **AlexaSkillFunctionArn**: The Lambda ARN to set as the Alexa skill endpoint.  
     - **SchedulerFunctionArn**: The Lambda ARN for RSS fetching, summarization, and notifications.

5. **Configure Alexa Skill**  
   - In the [**Alexa Developer Console**](https://developer.amazon.com/alexa/console/ask), open your skill and set the default endpoint to **AlexaSkillFunctionArn**.  
   - Ensure the **Skill ID** here matches the value of `AlexaSkillId` you passed to SAM.

---

## Post-Deployment Tasks

1. **Check Secrets**  
   - Confirm the Secrets Manager secret (`MyLLMApiSecret`) holds your LLM API credentials, for example:  
     ```json
     {
       "LLM_API_KEY": "...",
       "ALEXA_OAUTH_TOKEN": "..."
     }
     ```
   - If using Amazon Bedrock, adjust your scheduler code to call the Bedrock endpoint as needed.

2. **Test the Alexa Skill**  
   - In the Alexa Developer Console, use the **Test** tab or an Echo device.  
   - Try utterances like “Alexa, open FLRA Bot,” or “Alexa, ask FLRA Bot for the latest press releases.”

3. **Review Logs & Metrics**  
   - Check **CloudWatch Logs** for each Lambda (Scheduler, AlexaSkill).  
   - See **CloudWatch Metrics** under the custom namespace `FLRAAlexaSkill` for usage stats like `SkillInvocationCount` or `GetLatestUpdatesIntentCount`.

4. **Modify Feeds**  
   - Update `MULTIPLE_FEEDS` in `code/scheduler/app.py` to add/remove FLRA RSS sources.  
   - Commit and push changes to trigger an automated pipeline run (if configured).

---

## Contributing & Maintenance

- **Pull Requests**: Submit PRs to enhance or fix the solution.  
- **Issues**: Report bugs or request features via GitHub Issues.  
- **Versioning**: Use semantic versioning or tag releases for clarity.

---

## License

This project is distributed under the [MIT License](LICENSE). Refer to the license file for details.

---

## Additional Resources

- **AWS SAM**:  
  [AWS SAM Developer Guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html)
- **Alexa Developer Console**:  
  [Build Alexa Skills](https://developer.amazon.com/alexa/console/ask)
- **AWS CodeBuild**:  
  [Official Documentation](https://docs.aws.amazon.com/codebuild/latest/userguide/welcome.html)
- **AWS CodePipeline**:  
  [Official Documentation](https://docs.aws.amazon.com/codepipeline/latest/userguide/welcome.html)
- **Amazon Comprehend**:  
  [Developer Guide](https://docs.aws.amazon.com/comprehend/latest/dg/what-is.html)
- **Alexa Proactive Events API**:  
  [Reference Docs](https://developer.amazon.com/en-US/docs/alexa/notifications/notify-users.html)
