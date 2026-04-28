# Matching Threshold Recommendations

- `0.85+`: high-confidence violation, auto-alert
- `0.75-0.85`: medium confidence, send to dashboard review
- `0.70-0.75`: low confidence, log only
- `<0.70`: ignore

These thresholds should map to violation severity in the violations service. Final severity mapping must be confirmed with the backend team.
