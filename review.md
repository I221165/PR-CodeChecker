# Code Review: fix(skill): line-budget batching and split-on-output-limit retry
<https://github.com/Lum1104/Understand-Anything/pull/202>

**6 comments** (0 critical, 1 warnings, 5 suggestions)

---

## 🔒 Security
_(reviewer failed: InstructorRetryException: <failed_attempts>

<generation number="1">
<exception>
    litellm.RateLimitError: RateLimitError: GroqException - {"error":{"message":"Rate limit reached for model `llama-3.3-70b-versatile` in organization `org_01jnqhbthdfqrshzgc6z5rm2bq` service tier `on_demand` on tokens per minute (TPM): Limit 12000, Used 11742, Requested 2741. Please try again in 12.415s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing","type":"tokens","code":"rate_limit_exceeded"}}

</exception>
<completion>
    None
</completion>
</generation>

<generation number="2">
<exception>
    litellm.RateLimitError: RateLimitError: GroqException - {"error":{"message":"Rate limit reached for model `llama-3.3-70b-versatile` in organization `org_01jnqhbthdfqrshzgc6z5rm2bq` service tier `on_demand` on tokens per minute (TPM): Limit 12000, Used 11719, Requested 2741. Please try again in 12.299999999s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing","type":"tokens","code":"rate_limit_exceeded"}}

</exception>
<completion>
    None
</completion>
</generation>

<generation number="3">
<exception>
    litellm.RateLimitError: RateLimitError: GroqException - {"error":{"message":"Rate limit reached for model `llama-3.3-70b-versatile` in organization `org_01jnqhbthdfqrshzgc6z5rm2bq` service tier `on_demand` on tokens per minute (TPM): Limit 12000, Used 11689, Requested 2741. Please try again in 12.15s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing","type":"tokens","code":"rate_limit_exceeded"}}

</exception>
<completion>
    None
</completion>
</generation>

</failed_attempts>

<last_exception>
    litellm.RateLimitError: RateLimitError: GroqException - {"error":{"message":"Rate limit reached for model `llama-3.3-70b-versatile` in organization `org_01jnqhbthdfqrshzgc6z5rm2bq` service tier `on_demand` on tokens per minute (TPM): Limit 12000, Used 11689, Requested 2741. Please try again in 12.15s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing","type":"tokens","code":"rate_limit_exceeded"}}

</last_exception>)_

_No issues flagged._

## ⚡ Performance
_The PR addresses performance issues related to batch size and output limits. It introduces a line budget cap of ~2,500 total source lines per batch and a split-retry mechanism for output-limit failures. The changes are prompt-only and do not alter the codebase._

### 🔵 Line budget cap
_suggestion_ · `understand-anything-plugin/skills/understand/SKILL.md:281`-285

The added line budget cap of ~2,500 total source lines per batch helps prevent output token limits from being exceeded on output-constrained models. This change improves performance by avoiding unnecessary retries.

### 🔵 Split-retry mechanism
_suggestion_ · `understand-anything-plugin/skills/understand/SKILL.md:775`-780

The new split-retry mechanism for output-limit failures helps heal transient output overflows by splitting the failing batch in half and dispatching each half as a fresh batch. This change improves performance by reducing the number of retries and skips.

## 🎨 Style
_The PR contains two tweaks to the understand-anything-plugin/skills/understand/SKILL.md file, both of which are prompt-only changes with no code or schema changes. The changes are clear and well-explained, but there are no specific style or idiom violations in the provided diff._

_No issues flagged._

## 🧪 Tests
_The PR does not contain any code changes, only updates to the SKILL.md file. As a result, no new tests are required for this change. However, it would be beneficial to verify that the existing tests still cover the updated functionality and that the new batching strategy does not introduce any edge cases that are not exercised by the current tests._

### 🔵 Verify existing test coverage
_suggestion_ · `understand-anything-plugin/skills/understand/SKILL.md`

Although no new code is introduced, it's essential to ensure that the existing tests still cover the updated functionality, particularly the new batching strategy and split-on-output-limit retry.

**Suggested fix:**
```
Review the existing test suite to verify that it covers the updated functionality.
```

### 🔵 Consider adding tests for edge cases
_suggestion_ · `understand-anything-plugin/skills/understand/SKILL.md:281`-288

The new batching strategy may introduce edge cases that are not currently exercised by the tests. Consider adding tests to cover these scenarios, such as a batch with a single large file or a batch with multiple small files.

**Suggested fix:**
```
Add tests to cover edge cases, such as a batch with a single large file or a batch with multiple small files.
```

## 🛠️ Maintainability
_The PR improves the batching strategy by introducing a line budget cap and a split-on-output-limit retry mechanism. These changes enhance the maintainability of the code by reducing the likelihood of output token limit exceeded errors and improving the handling of large files. However, the changes are mostly prompt-only and do not modify the underlying code, so the maintainability concerns are relatively limited._

### 🔵 Consider adding a comment to explain the reasoning behind the 2,500 total-source-line cap
_suggestion_ · `understand-anything-plugin/skills/understand/SKILL.md:281`-288

The choice of 2,500 total source lines as the cap for each batch seems arbitrary and could be explained with a comment to improve understandability.

**Suggested fix:**
```
Add a comment above the line budget note to explain the reasoning behind the 2,500 total-source-line cap.
```

### 🟡 The split-on-output-limit retry mechanism could lead to recursive splits
_warning_ · `understand-anything-plugin/skills/understand/SKILL.md:775`-782

The split-on-output-limit retry mechanism could lead to recursive splits if the split batches still exceed the output token cap, which could lead to performance issues.

**Suggested fix:**
```
Consider adding a limit to the number of recursive splits to prevent performance issues.
```