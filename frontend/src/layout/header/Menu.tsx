
import styled from 'styled-components';
import {theme} from "../../styles/Theme.ts";


export type StrategySection = 'runs' | 'report' | 'registry' | 'config' | 'checks';

type MenuProps = {
  activeSection: StrategySection;
  onSectionChange: (section: StrategySection) => void;
};

const items: [StrategySection, string][] = [
  ['runs', 'Запуски'],
  ['report', 'Отчёт'],
  ['registry', 'Реестр'],
  ['checks', 'Проверки'],
  ['config', 'Настройки'],
];

export const Menu = ({ activeSection, onSectionChange }: MenuProps) => {
  const activeIndex = items.findIndex(([id]) => id === activeSection);

  return (
      <Navigation aria-label="Разделы StrategyLab">
        <Track>
          <ActiveIndicator
              aria-hidden="true"
              style={{ transform: `translateX(${activeIndex * 100}%)` }}
          />

          {items.map(([id, label]) => (
              <NavItem
                  key={id}
                  type="button"
                  aria-current={activeSection === id ? 'page' : undefined}
                  onClick={() => onSectionChange(id)}
              >
                {label}
              </NavItem>
          ))}
        </Track>
      </Navigation>
  );
};

const Navigation = styled.nav`
  width: min(100%, 580px);
  justify-self: center;
  overflow-x: auto;
  scrollbar-width: none;

  &::-webkit-scrollbar {
    display: none;
  }
`;

const Track = styled.div`
  position: relative;
  display: flex;
  align-items: center;
  box-sizing: border-box;
  min-width: 520px;
  height: 52px;
  padding: 5px;

  border-radius: 999px;
  background: ${theme.colors.accent};
  backdrop-filter: blur(24px);
`;

const ActiveIndicator = styled.span`
  position: absolute;
  top: 5px;
  left: 5px;
  width: calc((100% - 10px) / 5);
  height: calc(100% - 10px);

  border-radius: 999px;
  background: ${theme.colors.fontLight};
  pointer-events: none;
  transition: transform ${theme.animation.transition};

  @media (prefers-reduced-motion: reduce) {
    transition: none;
  }
`;

const NavItem = styled.button`
  position: relative;
  z-index: 1;
  flex: 1;
  min-width: 0;
  height: 100%;
  padding: 0 10px;

  border: none;
  border-radius: 999px;
  background: transparent;

  font-family: ${theme.fonts.interface};
  font-size: 12px;
  font-weight: 400;
  white-space: nowrap;
  color: ${theme.colors.fontLight};

  cursor: pointer;
  transition: color ${theme.animation.transition};

  &[aria-current='page'] {
    color: ${theme.colors.fontDark};
    font-weight: 600;
  }

  &:focus-visible {
    outline: 2px solid ${theme.colors.darkBgColor};
    outline-offset: -2px;
  }
`;
