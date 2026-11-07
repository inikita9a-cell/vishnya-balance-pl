import { useEffect, useState } from 'react';
import { Container } from './components/Container';
import { Header } from './layout/header/Header';
import type { StrategySection } from './layout/header/Menu';
import { Login } from './pages/login/Login';
import { Runs } from './pages/runs/Runs';
import { RunDetail } from './pages/runs/RunDetail';
import { Report } from './pages/report/Report';
import { Registry } from './pages/registry/Registry';
import { Checks } from './pages/checks/Checks';
import { Step } from './pages/steps/Step';
import { Config } from './pages/config/Config';
import { api, post } from './api/client';
import type { User } from './api/types';
import { getRuns } from './api/real';
import { isRunDone } from './api/format';
import { ErrorBox } from './components/Ui';
import { retainDeepLinkAfterLogin } from './api/deepLinks';
type Location = {
  section: StrategySection | 'detail' | 'step';
  runId: string;
  step: string;
  filters: Record<string, unknown>;
};
function parseFilters(value: string | null): Record<string, unknown> {
  if (!value || value.length > 1800) return {};
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch { return {}; }
}
function currentLocation(): Location {
  const params = new URLSearchParams(window.location.search);
  const section = params.get('page');
  const allowed = ['runs', 'report', 'registry', 'checks', 'config', 'detail', 'step'];
  return {
    section: allowed.includes(section ?? '') ? section as Location['section'] : 'runs',
    runId: params.get('run') || '',
    step: params.get('step') || '',
    filters: parseFilters(params.get('filters'))
  };
}
function App() {
  const [user, setUser] = useState<User | null>(null),
    [checking, setChecking] = useState(true),
    [location, setLocation] = useState<Location>(currentLocation),
    [error, setError] = useState('');
  useEffect(() => {
    api<User>('/me').then(setUser).catch(() => setUser(null)).finally(() => setChecking(false));
  }, []);
  useEffect(() => {
    const handler = () => setLocation(currentLocation());
    window.addEventListener('popstate', handler);
    return () => window.removeEventListener('popstate', handler);
  }, []);
  function navigate(section: Location['section'], runId = location.runId, step = '', filters: Record<string, unknown> = {}) {
    const next = {
      section,
      runId,
      step,
      filters
    };
    setLocation(next);
    const p = new URLSearchParams();
    p.set('page', section);
    if (runId) p.set('run', runId);
    if (step) p.set('step', step);
    if (Object.keys(filters).length) p.set('filters', JSON.stringify(filters));
    window.history.pushState({}, '', `?${p.toString()}`);
    window.scrollTo(0, 0);
  }
  async function selectSection(section: StrategySection) {
    if (['registry', 'report', 'checks'].includes(section) && !location.runId) {
      try {
        const result = await getRuns();
        const completed = result.filter(r => isRunDone(r.status)).sort((a, b) => b.created_at.localeCompare(a.created_at));
        if (completed.length) {
          navigate(section, completed[0].id);
          return;
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось загрузить запуски');
      }
      navigate('runs');
      return;
    }
    navigate(section);
  }
  async function start(configId: string) {
    try {
      const response = await post<{
        run_id: string;
      }>('/runs', { config_id: Number(configId) });
      navigate('detail', response.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось создать запуск');
    }
  }
  if (checking) return <div style={{ padding: 45, fontFamily: 'Manrope,sans-serif' }}>Подключение к StrategyLab…</div>;
  if (!user) return <Login onLogin={u => {
    setUser(u);
    if (!retainDeepLinkAfterLogin(location.section, location.runId)) navigate('runs', '');
  }} />;
  const section: StrategySection = ['report', 'registry', 'checks', 'config'].includes(location.section) ? location.section as StrategySection : 'runs';
  return <Container>
    <Header
      activeSection={section}
      onSectionChange={s => void selectSection(s)}
      userName={user.name}
      onLogout={() => {
        void post('/logout', {}).catch(() => { }).finally(() => {
          setUser(null);
          navigate('runs', '');
        });
      }} />
    {error && <ErrorBox>{error}</ErrorBox>}
    <main style={{ paddingBottom: 60 }}>
      {location.section === 'runs' && <Runs onOpen={id => navigate('detail', id)} />}
      {location.section === 'detail' && <RunDetail
        id={location.runId}
        onBack={() => navigate('runs')}
        onReport={() => navigate('report')}
        onRegistry={() => navigate('registry')}
        onChecks={() => navigate('checks')}
        onStep={key => navigate('step', location.runId, key)} />}
      {location.section === 'step' && <Step runId={location.runId} step={location.step} onBack={() => navigate('detail')} onHistory={() => navigate('runs')} />}
      {location.section === 'report' && <Report runId={location.runId} onRegistry={filters => navigate('registry', location.runId, '', filters)} />}
      {location.section === 'registry' && <Registry runId={location.runId} filters={location.filters} onRun={() => navigate('detail')} onRunChange={id => navigate('registry', id)} onClearFilters={() => navigate('registry', location.runId)} />}
      {location.section === 'checks' && <Checks runId={location.runId} />}
      {location.section === 'config' && <Config onStart={id => void start(id)} />}
    </main>
  </Container>;
}
export default App;
