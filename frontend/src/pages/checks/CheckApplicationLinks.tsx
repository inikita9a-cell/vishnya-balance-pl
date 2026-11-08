import { QuietButton } from '../../components/Ui';

export function CheckApplicationLinks({ appIds, onApplication, disabled = false }: {
  appIds: string[]; onApplication: (appId: string) => void; disabled?: boolean;
}) {
  return <ul style={{ display: 'flex', gap: 8, flexWrap: 'wrap', padding: 0, listStyle: 'none' }}>
    {appIds.map(id => <li key={id}>
      <QuietButton type="button" disabled={disabled} onClick={() => onApplication(id)}
        aria-label={`Открыть карточку заявки ${id}`} style={{ minHeight: 36, padding: '7px 12px' }}>
        {id} ↗
      </QuietButton>
    </li>)}
  </ul>;
}
