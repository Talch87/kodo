# TypeScript Agent Instructions

When working on TypeScript/JavaScript code in a React or Vite project:

## Before Modifying Code

1. **Understand the pattern**: Read the existing code carefully
   - Interface declarations must end with `{}`
   - Components must be properly exported
   - Import statements must be complete

2. **Check context**: Look at similar files to understand patterns
   - If `src/components/ui/textarea.tsx` has an interface pattern
   - Check `src/components/ui/command.tsx` to see if the same pattern applies

## When Fixing TypeScript Errors

### Common Patterns to Fix

#### Issue: Missing interface body
```typescript
// ❌ WRONG
export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement>

// ✅ CORRECT
export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}
```

**Critical**: When you fix this in one file, check if other files have the SAME pattern that needs fixing. Search for similar patterns:
- `grep -r "extends.*DialogProps$" src/`
- `grep -r "extends.*Attributes$" src/`

#### Issue: Missing export
```typescript
// ❌ WRONG
interface MyComponent { ... }

// ✅ CORRECT
export interface MyComponent { ... }
```

### After Every Modification

1. **Build verification** (REQUIRED):
   ```bash
   npm run build
   ```
   This MUST succeed before you declare the work complete.

2. **If build fails**:
   - Read the error carefully
   - Find the exact line/column
   - Verify your fix addresses the root cause (not just the symptom)
   - Re-test

3. **Check for side effects**:
   - Did you change a file that's imported elsewhere?
   - Did you modify an interface that other files depend on?
   - Run: `npm run build` (catches all issues)

### Pattern: Apply Fixes Consistently

When you find a pattern error (like missing interface body):

1. **Find all instances** of that pattern in the codebase
2. **Fix them ALL**, not just one
3. **Verify** the build succeeds after ALL fixes

**Example**:
- If you find `extends DialogProps` missing `{}` in one file
- Search for ALL files with that pattern
- Fix them all in one commit
- Verify build passes

## Verification Checklist

After completing work on TypeScript/JavaScript:
- [ ] `npm run build` succeeds
- [ ] No TypeScript errors
- [ ] No ESLint warnings (if running eslint)
- [ ] All imports are correct
- [ ] All interfaces/types have proper syntax
- [ ] Commit message is clear
