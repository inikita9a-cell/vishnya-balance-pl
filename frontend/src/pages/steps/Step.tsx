import { useEffect, useState } from 'react';
import styled from 'styled-components';
import { message } from '../../api/client';
import { getStepDetail } from '../../api/real';
import type { StepDetail } from '../../api/types';
import { stageLabel, status } from '../../api/format';
import { PageHeading, Panel, ErrorBox, Tag, Muted, NoticeSpacing } from '../../components/Ui';
import { InfoNotice } from '../../components/InfoNotice/InfoNotice';
import { Breadcrumbs } from '../../components/Breadcrumbs';
type Props = { runId: string; step: string; onBack: () => void; onHistory: () => void };
export function Step({ runId, step, onBack, onHistory }: Props) {
  const [detail, setDetail] = useState<StepDetail | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    setDetail(null); setError('');
    getStepDetail(runId, step)
      .then(r => { if (live) setDetail(r); })
      .catch(e => { if (live) setError(message(e)); });
    return () => { live = false; };
  }, [runId, step]);
  return <>
    <Breadcrumbs items={[{ label: 'История запусков', onClick: onHistory }, { label: `Запуск ${runId}`, onClick: onBack }, { label: stageLabel(step) }]} />
    <PageHeading><div><h1>{stageLabel(step)}</h1><p>Запуск {runId} · этап {step}</p></div>
      {detail && <Tag $tone={detail.log.status === 'done' ? 'good' : detail.log.status === 'failed' ? 'bad' : 'busy'}>{status(detail.log.status)}</Tag>}
    </PageHeading>
    <NoticeSpacing><InfoNotice title="Как читать детали этапа" defaultOpen={false}>
      <p>Вы смотрите отдельный этап обработки запуска <strong>{runId}</strong>. Здесь отображаются описание, параметры, снимок кода и технический журнал из API. Хлебные крошки выше возвращают к запуску и его истории.</p>
    </InfoNotice></NoticeSpacing>
    {error && <ErrorBox role="alert">{error}</ErrorBox>}
    {!detail && !error && <Muted>Загружаем этап…</Muted>}
    {detail && <Panel>
      <Section><h2>Описание</h2><p>{detail.docstring || 'Описание этапа не предоставлено.'}</p></Section>
      <Section><h2>Параметры выполнения</h2><CodePreview $dark={false}>{JSON.stringify(detail.params, null, 2)}</CodePreview></Section>
      <Section><h2>Исходный код этапа</h2><CodePreview $dark>{detail.code}</CodePreview></Section>
      <Section><h2>Журнал выполнения</h2><CodePreview $dark={false}>{JSON.stringify(detail.log, null, 2)}</CodePreview></Section>
    </Panel>}
  </>;
}
const Section = styled.section` background: transparent; &:not(:last-child) { padding-bottom: 25px; margin-bottom: 25px; border-bottom: 1px solid #efeff1; } h2 { font: 700 14px 'Wix Madefor Display',sans-serif; margin-bottom: 13px; } p { font-size: 13px; font-weight: 400; } `;
const CodePreview = styled.pre<{ $dark: boolean }>` background: ${p => p.$dark ? '#181824' : '#f7f7f9'}; color: ${p => p.$dark ? '#f5f5f8' : '#575761'}; border-radius: 13px; padding: 20px; font: 400 12px/1.7 monospace; overflow-x: auto; white-space: pre-wrap; overflow-wrap: anywhere; `;
