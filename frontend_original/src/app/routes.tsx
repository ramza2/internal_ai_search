import { createBrowserRouter } from 'react-router-dom';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { SearchPage } from './pages/SearchPage';
import { AISearchPage } from './pages/AISearchPage';
import { FileDetailPage } from './pages/FileDetailPage';
import { DashboardPage } from './pages/admin/DashboardPage';
import { DataSourceSettingsPage } from './pages/admin/DataSourceSettingsPage';
import { FileAnalyticsPage } from './pages/admin/FileAnalyticsPage';
import { IndexingPage } from './pages/admin/IndexingPage';
import { ExclusionPolicyPage } from './pages/admin/ExclusionPolicyPage';
import { UsersPage } from './pages/admin/UsersPage';
import { LogsPage } from './pages/admin/LogsPage';
import { FailedFilesPage } from './pages/admin/FailedFilesPage';
import { RAGSettingsPage } from './pages/admin/RAGSettingsPage';
import { DuplicateDetectionPage } from './pages/admin/DuplicateDetectionPage';
import { NotFoundPage } from './pages/NotFoundPage';

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />
  },
  {
    path: '/register',
    element: <RegisterPage />
  },
  {
    path: '/',
    element: <SearchPage />
  },
  {
    path: '/ai-search',
    element: <AISearchPage />
  },
  {
    path: '/file/:id',
    element: <FileDetailPage />
  },
  {
    path: '/admin/dashboard',
    element: <DashboardPage />
  },
  {
    path: '/admin/datasource-settings',
    element: <DataSourceSettingsPage />
  },
  {
    path: '/admin/owncloud-settings',
    element: <DataSourceSettingsPage />
  },
  {
    path: '/admin/file-analytics',
    element: <FileAnalyticsPage />
  },
  {
    path: '/admin/indexing',
    element: <IndexingPage />
  },
  {
    path: '/admin/exclusion-policy',
    element: <ExclusionPolicyPage />
  },
  {
    path: '/admin/users',
    element: <UsersPage />
  },
  {
    path: '/admin/logs',
    element: <LogsPage />
  },
  {
    path: '/admin/failed-files',
    element: <FailedFilesPage />
  },
  {
    path: '/admin/rag-settings',
    element: <RAGSettingsPage />
  },
  {
    path: '/admin/duplicate-detection',
    element: <DuplicateDetectionPage />
  },
  {
    path: '*',
    element: <NotFoundPage />
  }
]);
