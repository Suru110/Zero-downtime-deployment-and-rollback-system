import React, { useState } from 'react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ToastProvider } from './contexts/ToastContext';
import { Navbar } from './components/Navbar';
import { Sidebar, NavTab } from './components/Sidebar';
import { DashboardOverview } from './pages/DashboardOverview';
import { ApplicationsPage } from './pages/ApplicationsPage';
import { DeploymentsPage } from './pages/DeploymentsPage';
import { AuditLogsPage } from './pages/AuditLogsPage';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { DeploymentModal } from './components/DeploymentModal';
import { Project, Environment, Release } from './types';
import api from './api/client';

const AppContent: React.FC = () => {
  const { isAuthenticated, isReady } = useAuth();
  const [path, setPath] = useState(window.location.pathname);
  const [currentTab, setCurrentTab] = useState<NavTab>('overview');
  const [activeDeploymentId, setActiveDeploymentId] = useState<string | null>(null);

  // Deployment modal state
  const [deployProject, setDeployProject] = useState<Project | null>(null);
  const [modalEnvs, setModalEnvs] = useState<Environment[]>([]);
  const [modalReleases, setModalReleases] = useState<Release[]>([]);

  React.useEffect(() => {
    const handlePopState = () => setPath(window.location.pathname);
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  if (!isReady) {
    return <div className="min-h-screen bg-slate-950" />;
  }
  if (!isAuthenticated) {
    return path === '/register' ? <RegisterPage /> : <LoginPage />;
  }

  const handleOpenDeployModal = async (project: Project) => {
    try {
      const [envRes, relRes] = await Promise.all([
        api.get(`/projects/${project.id}/environments`),
        api.get(`/projects/${project.id}/releases`)
      ]);
      setDeployProject(project);
      setModalEnvs(envRes.data.data);
      setModalReleases(relRes.data.data);
    } catch (err) {
      console.error('Failed to load project details for deployment modal:', err);
    }
  };

  const handleSelectDeploymentFromFeed = (depId: string) => {
    setActiveDeploymentId(depId);
    setCurrentTab('deployments');
  };

  return (
    <div className="min-h-screen bg-[#030712] flex flex-col">
      <Navbar />

      <div className="flex-1 flex overflow-hidden">
        <Sidebar currentTab={currentTab} onTabChange={setCurrentTab} />

        <main className="flex-1 overflow-y-auto p-6 md:p-8">
          <div className="max-w-7xl mx-auto">
            {currentTab === 'overview' && (
              <DashboardOverview
                onOpenDeployModal={handleOpenDeployModal}
                onSelectDeployment={handleSelectDeploymentFromFeed}
              />
            )}
            {currentTab === 'applications' && (
              <ApplicationsPage onOpenDeployModal={handleOpenDeployModal} />
            )}
            {currentTab === 'deployments' && (
              <DeploymentsPage initialSelectedId={activeDeploymentId} />
            )}
            {currentTab === 'audit' && (
              <AuditLogsPage />
            )}
          </div>
        </main>
      </div>

      {deployProject && (
        <DeploymentModal
          isOpen={!!deployProject}
          onClose={() => setDeployProject(null)}
          project={deployProject}
          environments={modalEnvs}
          releases={modalReleases}
          onReleaseCreated={(release) => setModalReleases((current) => [release, ...current])}
          onDeploymentTriggered={() => {
            setCurrentTab('deployments');
          }}
        />
      )}
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <ToastProvider>
        <AppContent />
      </ToastProvider>
    </AuthProvider>
  );
};

export default App;
