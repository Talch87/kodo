# Kodo UI - Web Interface for Autonomous Coding Agent

A modern React/Next.js dashboard for managing and monitoring Kodo autonomous coding agent runs.

## Features

- **Dashboard** - Real-time monitoring of code generation progress
- **Run Management** - History of all Kodo runs with status tracking
- **Agent Monitor** - Performance metrics for each agent (Worker, Architect, Tester, Designer)
- **Cost Tracking** - Track API spending per agent and run
- **Execution Timeline** - Visual representation of task execution progress
- **Goal Input** - Submit new coding goals to Kodo
- **Responsive Design** - Works on desktop, tablet, and mobile

## Getting Started

### Prerequisites

- Node.js 18+ 
- npm or yarn

### Installation

```bash
cd kodo-ui
npm install
```

### Development

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Build

```bash
npm run build
npm start
```

## Project Structure

```
kodo-ui/
├── app/
│   ├── page.tsx          # Main dashboard page
│   ├── layout.tsx        # Root layout
│   └── globals.css       # Global styles
├── components/
│   ├── Sidebar.tsx       # Navigation sidebar
│   ├── Header.tsx        # Top header
│   ├── GoalInput.tsx     # Goal submission form
│   ├── Dashboard.tsx     # Stats dashboard
│   ├── RunsList.tsx      # List of runs
│   ├── AgentMonitor.tsx  # Agent performance
│   ├── CostTracker.tsx   # Cost analysis
│   └── ExecutionTimeline.tsx # Task execution timeline
├── lib/
│   └── store.ts          # Zustand state management
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── next.config.js
```

## Technologies

- **React 18** - UI framework
- **Next.js 14** - React framework with SSR
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **Zustand** - State management
- **Lucide React** - Icons

## API Integration

This UI is designed to work with a Kodo backend API. You'll need to connect:

1. `POST /api/runs` - Create a new run
2. `GET /api/runs/:id` - Get run details
3. `GET /api/agents` - Get agent status
4. `GET /api/cost` - Get cost information
5. `WebSocket /api/runs/:id/stream` - Stream real-time updates

## Styling

The UI uses Tailwind CSS with custom components:

- `.card` - Card component
- `.badge` - Badge component
- `.btn` - Button component
- `.input` - Input component
- `.progress-bar` - Progress bar component

## License

MIT
