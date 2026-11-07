import styled from 'styled-components';
import { Surface } from '../../../components/Surface';
import { AppSelect } from '../../../components/AppSelect/AppSelect';
import { theme } from '../../../styles/Theme';
export type RegistryStatus = 'all' | 'approved' | 'declined' | 'review';
type Props = {
  searchQuery: string;
  onSearchChange: (value: string) => void;
  status: RegistryStatus;
  onStatusChange: (value: RegistryStatus) => void;
};
const statusOptions = [
  { value: 'all', label: 'Все решения' },
  { value: 'approved', label: 'Одобрено' },
  { value: 'declined', label: 'Отказ' },
  { value: 'review', label: 'На проверке' }
];
export function RegistryFilters({ searchQuery, onSearchChange, status, onStatusChange }: Props) {
  return <FilterBar>
    <Search>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
      <input type="search" value={searchQuery} onChange={e => onSearchChange(e.target.value)} aria-label="Поиск по идентификатору заявки" placeholder="Поиск по ID заявки" />
      {searchQuery && <Clear type="button" onClick={() => onSearchChange('')} aria-label="Очистить поиск">×</Clear>}
    </Search>
    <SelectWrap><AppSelect ariaLabel="Фильтр по решению" value={status} options={statusOptions} onChange={v => onStatusChange(v as RegistryStatus)} /></SelectWrap>
  </FilterBar>;
}
const FilterBar = styled(Surface)`
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  position: relative; z-index: 10;
  padding: 17px 24px; min-height: 80px;
  @media (max-width: 640px) { padding: 17px; }
`;
const Search = styled.label`
  display: flex; align-items: center; gap: 10px; flex: 1 1 260px; min-width: 0;
  height: 46px; padding: 0 16px; border: 1px solid #e5e5e9; border-radius: 15px;
  background: #fff; color: #9898a2;
  &:focus-within { border-color: ${theme.colors.accent}; }
  input { flex: 1; min-width: 0; width: 100%; outline: none; border: none; background: transparent; font: 500 13px ${theme.fonts.interface}; }
  input::placeholder { color: #9898a2; }
`;
const Clear = styled.button`
  background: none; border: none; font-size: 18px; color: #92929b; cursor: pointer;
  &:hover { color: ${theme.colors.accent}; }
`;
const SelectWrap = styled.div` flex: 0 1 245px; min-width: 185px; @media (max-width: 600px) { flex: 1 1 100%; } `;
