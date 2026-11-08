import { useEffect, useState } from 'react';
import styled from 'styled-components';
import { message, post, put } from '../../api/client';
import { getConfigs, getPools, getProcedures, createTemplateConfig } from '../../api/real';
import type { Config as ConfigType, Pool, Procedure } from '../../api/types';
import { PageHeading, Panel, Line, PrimaryButton, QuietButton, Field, ErrorBox, Muted, NoticeSpacing } from '../../components/Ui';
import { InfoNotice } from '../../components/InfoNotice/InfoNotice';
import { AppSelect } from '../../components/AppSelect/AppSelect';
import { theme } from '../../styles/Theme';

type Props = { onStart: (id: string) => void };
export function Config({ onStart }: Props) {
  const [configs, setConfigs] = useState<ConfigType[]>([]);
  const [pools, setPools] = useState<Pool[]>([]);
  const [procedures, setProcedures] = useState<Procedure[]>([]);
  const [current, setCurrent] = useState('');
  const [name, setName] = useState('');
  const [yaml, setYaml] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      const [a, b, c] = await Promise.all([getConfigs(), getPools(), getProcedures()]);
      setConfigs(a); setPools(b); setProcedures(c);
      setCurrent(v => a.some(i => i.id === v) ? v : a[0]?.id ?? '');
      setError('');
    } catch (e) { setError(message(e)); }
  }
  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    const item = configs.find(c => c.id === current);
    if (item) { setName(item.name); setYaml(item.yaml); }
  }, [current, configs]);

  async function save(asNew: boolean) {
    setError(''); setNotice('');
    if (!name.trim()) { setError('Укажите название конфигурации.'); return; }
    if (!yaml.trim()) { setError('YAML конфигурации не может быть пустым.'); return; }
    setBusy(true);
    try {
      // The backend expects a string field named 'yaml', not a JSON config object.
      const payload = { name: name.trim(), yaml };
      if (asNew) {
        const created = await post<{ id: number }>('/configs', payload);
        await refresh(); setCurrent(String(created.id));
      } else {
        await put<{ ok: boolean }>(`/configs/${encodeURIComponent(current)}`, payload);
        await refresh();
      }
      setNotice('Конфигурация сохранена на FastAPI.');
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }

  async function createDefault() {
    setBusy(true); setError(''); setNotice('');
    try {
      const created = await createTemplateConfig();
      await refresh(); setCurrent(String(created.id));
      setNotice('Создан пресет из серверного шаблона. Проверьте dataset.path перед запуском.');
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeading><div><h1>Конфигурации анализа</h1><p>Пресеты, пулы заявок и процедуры сравнения</p></div></PageHeading>
    <NoticeSpacing><InfoNotice title="Как работают настройки анализа">
      <p>Пресет — это YAML-конфигурация движка: путь к данным, набор заявок, нормализация, сравнение и проверки. Создайте стандартный пресет из шаблона бэкенда, затем настройте его под свой датасет.</p>
      <p>Изменения сохранённого пресета влияют только на новые запуски. У уже запущенного анализа бэкенд сохраняет снимок YAML. Пулы и процедуры ниже — отдельные справочники API, их ID пока не выбираются при создании запуска.</p>
    </InfoNotice></NoticeSpacing>
    {error && <ErrorBox role="alert">{error}</ErrorBox>}
    {notice && <SavedNotice role="status">{notice}</SavedNotice>}
    <EditorPanel>
      <PanelTitle><h2>Параметры анализа</h2><Muted>YAML из реального FastAPI</Muted></PanelTitle>
      <FormGrid>
        <FormGroup><FieldLabel as="div">Пресет</FieldLabel>
          <AppSelect ariaLabel="Выбрать пресет анализа" value={current} onChange={setCurrent} disabled={busy}
            options={configs.map(c => ({ value: c.id, label: c.name }))} placeholder="Выберите пресет" />
        </FormGroup>
        <FormGroup><FieldLabel htmlFor="configuration-name">Название</FieldLabel>
          <Field id="configuration-name" value={name} onChange={e => setName(e.target.value)} placeholder="Название конфигурации" disabled={busy} />
        </FormGroup>
      </FormGrid>
      <FormGroup><FieldLabel htmlFor="configuration-yaml">YAML конфигурации</FieldLabel>
        <JsonEditor id="configuration-yaml" spellCheck={false} value={yaml} onChange={e => setYaml(e.target.value)} disabled={busy} aria-label="YAML конфигурации" placeholder="Сначала создайте пресет из серверного шаблона" />
      </FormGroup>
      <Actions>
        <Line>
          <PrimaryButton type="button" disabled={busy || !current || !name.trim() || !yaml.trim()} onClick={() => void save(false)}>Сохранить</PrimaryButton>
          <QuietButton type="button" disabled={busy || !name.trim() || !yaml.trim()} onClick={() => void save(true)}>Создать копию</QuietButton>
          <QuietButton type="button" disabled={busy} onClick={() => void createDefault()}>Создать из шаблона</QuietButton>
          <QuietButton type="button" disabled={busy || !current} onClick={() => onStart(current)}>Запустить с пресетом →</QuietButton>
        </Line>
        <Muted>Путь dataset.path относится к компьютеру с бэкендом, не к браузеру.</Muted>
      </Actions>
    </EditorPanel>
    <CatalogPanel>
      <CatalogHeader><h2>Справочники анализа</h2><Muted>Данные из FastAPI</Muted></CatalogHeader>
      <CatalogGrid>
        <CatalogList><h3>Пулы заявок <Count>{pools.length}</Count></h3>
          {pools.map(pool => <CatalogRow key={pool.id}><strong>{pool.name}</strong><span>{pool.id} · {pool.mode}</span></CatalogRow>)}
          {!pools.length && <Muted>Пулы не найдены</Muted>}
        </CatalogList>
        <CatalogList><h3>Процедуры <Count>{procedures.length}</Count></h3>
          {procedures.map(proc => <CatalogRow key={proc.id}><strong>{proc.name}</strong><span>{proc.id} · {proc.kind}</span></CatalogRow>)}
          {!procedures.length && <Muted>Процедуры не найдены</Muted>}
        </CatalogList>
      </CatalogGrid>
    </CatalogPanel>
  </>;
}
const EditorPanel = styled(Panel)` margin-bottom: 20px; padding: 27px; `;
const PanelTitle = styled.div` display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 23px; h2 { font: 700 15px ${theme.fonts.interface}; } `;
const FormGrid = styled.div` display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 18px; margin-bottom: 21px; @media (max-width: 700px) { grid-template-columns: 1fr; } `;
const FormGroup = styled.div` min-width: 0; `;
const FieldLabel = styled.label` display: block; font: 500 12px ${theme.fonts.interface}; color: #777782; margin-bottom: 10px; `;
const JsonEditor = styled.textarea`
  display: block; width: 100%; min-height: 325px; resize: vertical;
  padding: 21px 23px; border: 1px solid #e5e5e9; border-radius: 15px;
  background: #181824; color: #f1f1f4; font: 400 12px/1.75 monospace;
  &:focus-visible { outline: 2px solid ${theme.colors.accent}; outline-offset: 2px; }
`;
const Actions = styled.div`
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;
  gap: 18px; margin-top: 22px;
`;
const SavedNotice = styled.p` color: #278259; font-size: 12px; margin-bottom: 16px; `;
const CatalogPanel = styled(Panel)` padding: 0; overflow: hidden; `;
const CatalogHeader = styled(PanelTitle)` margin: 0; padding: 24px 27px; border-bottom: 1px solid #efeff1; `;
const CatalogGrid = styled.div` display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); @media (max-width: 700px) { grid-template-columns: 1fr; } `;
const CatalogList = styled.div`
  min-width: 0; padding: 23px 27px;
  & + & { border-left: 1px solid #efeff1; }
  h3 { display: flex; gap: 12px; align-items: center; font: 650 13px ${theme.fonts.interface}; margin-bottom: 17px; }
  @media (max-width: 700px) { & + & { border-left: 0; border-top: 1px solid #efeff1; } }
`;
const Count = styled.span` color: #9696a1; font: 400 12px ${theme.fonts.interface}; `;
const CatalogRow = styled.div`
  padding: 13px 0; border-top: 1px solid #f1f1f3;
  strong { display: block; font: 600 12px ${theme.fonts.interface}; }
  span { display: block; font: 400 11px ${theme.fonts.interface}; color: #9999a3; margin-top: 6px; overflow-wrap: anywhere; }
`;
