import styled from 'styled-components';
import { theme } from '../styles/Theme';

type Crumb = { label: string; onClick?: () => void };
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return <Nav aria-label="Навигационная цепочка">
    <ol>{items.map((item, index) => <li key={`${item.label}-${index}`}>
      {index > 0 && <span aria-hidden="true" className="separator">/</span>}
      {item.onClick
        ? <button type="button" onClick={item.onClick}>{item.label}</button>
        : <span aria-current="page">{item.label}</span>}
    </li>)}</ol>
  </Nav>;
}
const Nav = styled.nav`
  margin: 8px 0 22px;
  ol { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  li { display: flex; align-items: center; gap: 10px; font: 500 12px ${theme.fonts.interface}; }
  .separator { color: #b9b9c0; }
  span[aria-current] { color: ${theme.colors.darkBgColor}; }
  button { padding: 3px 0; background: transparent; border: none; cursor: pointer; color: #898993; font: inherit; }
  button:hover { color: ${theme.colors.accent}; }
  button:focus-visible { outline: 2px solid ${theme.colors.accent}; outline-offset: 3px; }
`;
