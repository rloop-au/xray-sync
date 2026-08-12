# Security

Please report security issues privately rather than opening a public issue.

xray-sync handles Jira API tokens and Xray client credentials. The codebase should never persist credentials to exports, plans, logs, checkpoints, reports, or test fixtures. If you find a leak path, treat it as a security issue.
