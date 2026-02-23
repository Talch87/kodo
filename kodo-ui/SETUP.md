# Kodo UI Setup Guide

## Quick Start

### 1. Install Dependencies

```bash
cd kodo-ui
npm install
```

### 2. Run Development Server

```bash
npm run dev
```

Visit http://localhost:3000

### 3. Features Available

- ✅ Submit goals for Kodo to work on
- ✅ Real-time progress tracking
- ✅ Agent performance monitoring
- ✅ Cost tracking and budget management
- ✅ Run history and status
- ✅ Execution timeline visualization

## Backend Integration

To fully connect to Kodo, implement these API endpoints:

### WebSocket Stream (Real-time Updates)

```javascript
// Client-side example
const ws = new WebSocket('ws://localhost:8000/api/runs/run-123/stream')

ws.onmessage = (event) => {
  const update = JSON.parse(event.data)
  // Update UI with: progress, cycles, cost, status
}
```

### REST API Endpoints

```bash
# Submit a goal
POST /api/runs
{
  "goal": "Create a REST API for todo items",
  "model": "claude-opus",
  "budget": 10.00
}

# Get run status
GET /api/runs/:id

# List all runs
GET /api/runs

# Get agent metrics
GET /api/agents

# Get cost report
GET /api/cost
```

## Customization

### Change Colors

Edit `tailwind.config.js`:
```javascript
colors: {
  primary: '#YOUR_COLOR',
  secondary: '#YOUR_COLOR',
}
```

### Add New Views

1. Create component in `components/`
2. Add to sidebar in `Sidebar.tsx`
3. Add view handler in `app/page.tsx`

### Connect Real Kodo Backend

1. Create an API client in `lib/api.ts`
2. Replace mock data in components with real API calls
3. Update WebSocket URL in components

## Deployment

### Deploy to Vercel (Recommended)

```bash
vercel deploy
```

### Deploy to Other Platforms

```bash
npm run build
npm start
```

## Troubleshooting

**Port 3000 already in use:**
```bash
npm run dev -- -p 3001
```

**Tailwind styles not loading:**
```bash
npm run build
```

**TypeScript errors:**
```bash
npm run lint
```

## Next Steps

1. Connect to real Kodo backend API
2. Add WebSocket support for real-time updates
3. Implement authentication
4. Add dark mode
5. Add export/report generation
6. Add agent configuration UI
