Automatic message from `scripts/overnight/gpt-quota-probe.ps1 -Name go`: **the opencode-go quota has reset** (a probe to `opencode-go/gemini-4-argon` just succeeded; the time is in `.scratch/local-overnight/go-available.json`). D13e is lifted. From now on:

1. **Gemini 4 Argon** (`opencode-go/gemini-4-argon#medium`) can take back the Gemini roles: the second reviewer on must-fix delta reviews, the rule-audit passes, and one of the final-review reviewers, alongside GPT-6.1 Sol. That takes load off the Sol quota.
2. **GPT-6 Luna** (`opencode-go/gpt-6-luna#medium`) is the fallback second reviewer if Sol hits its limit.
3. Keep at most 6 concurrent opencode-go sessions. The quota ran out once already (Sat ~07:05), so spend it on reviews only, never on implementation.
4. If opencode-go fails with a usage limit again, go straight back to the D13e roster and log it.
Log the switch (D13e lifted) and write a heartbeat.
