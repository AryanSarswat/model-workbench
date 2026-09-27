import type { RouteObject } from 'react-router'
import { AppShell } from './components/AppShell'
import { RouteError } from './components/RouteError'
import DatasetPage from './pages/dataset/DatasetPage'
import EvalsPage from './pages/evals/EvalsPage'
import LibraryPage from './pages/library/LibraryPage'
import ModelPage from './pages/model/ModelPage'
import NotFoundPage from './pages/not-found/NotFoundPage'
import PlaygroundPage from './pages/playground/PlaygroundPage'
import RadarPage from './pages/radar/RadarPage'
import ReviewPage from './pages/review/ReviewPage'

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    errorElement: <RouteError />, // the shell itself failed (e.g. the top bar)
    children: [
      {
        errorElement: <RouteError />, // a page failed: shown inside the shell, nav still works
        children: [
          { path: '/', element: <RadarPage /> },
          { path: '/models/:author/:name', element: <ModelPage /> },
          { path: '/playground', element: <PlaygroundPage /> }, // reads ?model=&backend=&quant=
          { path: '/evals', element: <EvalsPage /> },
          { path: '/evals/runs/:runId', element: <ReviewPage /> },
          { path: '/dataset', element: <DatasetPage /> },
          { path: '/library', element: <LibraryPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]
