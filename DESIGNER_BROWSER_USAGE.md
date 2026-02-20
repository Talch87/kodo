# Designer Browser Agent - Usage Guide

## Overview

The `designer_browser` agent is a new addition to Kodo's team that can **visually inspect and improve web UIs** by:
- Opening your web app in a real browser
- Taking screenshots to see the current state
- Clicking buttons, filling forms, testing interactions
- Identifying visual/UX problems (spacing, colors, responsive issues)
- Making CSS and component improvements directly
- Verifying fixes with new screenshots

## When to Use

Use `designer_browser` when you need:
- **Visual design review** — Spacing, alignment, colors, typography
- **Responsive design testing** — Mobile, tablet, desktop layouts
- **Interaction testing** — Forms, buttons, navigation, state changes
- **Accessibility review** — Keyboard navigation, color contrast, ARIA
- **UI improvements** — Fix broken layouts, improve consistency
- **UX validation** — Ensure features work as expected from user perspective

## How to Use

### Basic Usage

```
orchestrator: ask_designer_browser
task: "Review the Covenance website design. Check for responsive behavior on mobile/tablet/desktop. Fix any spacing or color issues you find."
```

### Specific Review Requests

#### Visual Design Review
```
"Visit the website and take screenshots at different screen widths (mobile, tablet, desktop). 
Check for:
- Proper spacing and alignment (buttons, text, cards)
- Font sizes and hierarchy
- Color contrast and consistency
- Responsive layout (no overflow, proper scaling)

Take before/after screenshots and commit improvements."
```

#### Interaction Testing
```
"Test the login form. Click buttons, fill text fields, test error states. 
Check that:
- Form labels are clear and associated with inputs
- Error messages are visible and helpful
- Submit button works correctly
- Form resets after submission

Fix any broken interactions or missing states."
```

#### Accessibility Review
```
"Test the navigation and forms for accessibility:
- Can you navigate the entire site using only Tab key?
- Are all interactive elements keyboard accessible?
- Do buttons have proper ARIA labels?
- Is color contrast sufficient (WCAG AA standard)?

Fix any accessibility issues found."
```

### Output Expectations

The designer_browser agent will:
1. **Start the app** — Build/run the dev server as needed
2. **Take screenshots** — Capture current visual state
3. **Test interactions** — Click, type, navigate, observe behavior
4. **Identify issues** — Note spacing, color, responsiveness, accessibility problems
5. **Apply fixes** — Modify CSS/components to address issues
6. **Take verification screenshots** — Show that fixes worked
7. **Commit changes** — Git commit with clear messages

Example output:
```
[browser] Opening http://localhost:5173
[screenshot] Desktop view: /tmp/kodo-screenshot-1.png
[issue] Hero section padding too large on mobile (200px vs 40px)
[fix] Updated src/components/Hero.tsx padding: {desktop: '200px', mobile: '40px'}
[screenshot] Mobile view fixed: /tmp/kodo-screenshot-2.png
[✓] Spacing fixed - hero padding now responsive
[✓] Committed: "fix: make hero section responsive on mobile"
```

## Example: Improve Covenance Website

### Full UI Improvement Request

```
task: "Improve the Covenance website UI:

1. Open the website at http://localhost:5173
2. Take screenshots at mobile (375px), tablet (768px), and desktop (1440px) widths
3. Check for issues:
   - Text readability (font sizes, line heights)
   - Spacing consistency (padding, margins)
   - Button/CTA prominence and usability
   - Color contrast (WCAG AA standard)
   - Responsive behavior (no overflow, proper scaling)
4. Fix at least 3 issues directly (CSS changes)
5. Test improvements with new screenshots
6. Commit with clear messages"
```

## Tips for Best Results

### 1. Be Specific
Good: "Fix spacing on mobile (inputs are 8px apart, should be 16px)"
Bad: "Make the UI look better"

### 2. Provide Context
If fixing a specific component, mention it:
- "Fix the ContactForm component in src/components/ContactForm.tsx"
- "Improve mobile layout for the hero section"
- "Test the Stripe payment form interaction"

### 3. Test After Changes
Ask the agent to:
- Take screenshots showing the fix
- Test on multiple screen sizes
- Verify no new issues were introduced

### 4. Use for Iteration
Run multiple times:
1. First pass: Major layout/spacing issues
2. Second pass: Color/typography refinement
3. Third pass: Accessibility and edge cases

## Browser Capabilities

The designer_browser agent has access to:
- **Visual inspection** — Screenshots, dimensions, colors
- **Interaction** — Click, type, hover, scroll, form submission
- **Accessibility testing** — Tab navigation, keyboard shortcuts
- **Console access** — Check for JS errors, warnings
- **Network inspection** — Monitor API calls (basic)
- **Responsive testing** — Resize viewport to different screen sizes

## Limitations

The designer_browser agent:
- ❌ Cannot install dependencies (ask worker to do that first)
- ❌ Cannot run long-running tests
- ❌ Cannot test complex user flows (use tester_browser for that)
- ❌ May not catch subtle color differences in screenshots
- ⚠️ Works best on modern web frameworks (React, Vue, Svelte, etc.)

## Combining with Other Agents

### With Worker
```
1. worker: "Build new landing page section with 3 feature cards"
2. designer_browser: "Review the new landing page. Fix spacing and alignment"
3. tester_browser: "Test that all cards are clickable and links work"
```

### With Architect
```
1. designer_browser: "Screenshot and review current component structure"
2. architect: "Review the CSS organization. Suggest refactoring"
3. worker: "Refactor components based on architect feedback"
4. designer_browser: "Verify visual output is identical after refactoring"
```

## Troubleshooting

### "Browser failed to open"
- Check that the dev server is running (`npm run dev`)
- Verify the port in the task matches your setup
- Try a different port if 5173 is in use

### "Screenshots are empty/gray"
- The page may still be loading (give it more time)
- Check console errors in the app
- Try refreshing the page

### "Changes didn't apply visually"
- The agent modified the right file but changes need rebuild
- Check if you're using Vite hot reload (should be automatic)
- Sometimes a full rebuild is needed

### "Color contrast still failing"
- Designer_browser may struggle with subtle color differences
- Provide specific color values: "Button text should be #000000 on #FFFFFF"
- Use validated color tools (WebAIM, WAVE) for verification

## Integration with Kodo Workflows

Example full workflow:
```
Goal: "Improve Covenance website UI and ensure it's production-ready"

1. worker: "Build and run dev server"
2. designer_browser: "Take screenshots and identify 5 biggest UI issues"
3. worker: "Fix the issues designer_browser found"
4. designer_browser: "Verify fixes look good. Test responsive behavior"
5. tester_browser: "Test all user interactions and forms"
6. architect: "Review CSS organization and component structure"
7. worker: "Refactor based on architect recommendations"
8. designer_browser: "Final check - verify visual quality is maintained"
9. orchestrator: "Done - website is improved and tested"
```

## Next Steps

- **Run it:** `kodo . --goal "Review and improve website design"`
- **Iterate:** Use multiple passes for different aspects (layout → colors → interactions)
- **Combine:** Use with other agents for comprehensive reviews
- **Automate:** Use in CI/CD for continuous design quality checks (future enhancement)
