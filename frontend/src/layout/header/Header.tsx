
import styled from 'styled-components';
import { theme } from '../../styles/Theme.ts';
import { Logo } from '../../components/Logo/testLogo.tsx';
import { Menu, type StrategySection } from './Menu';

type HeaderProps = {
    activeSection: StrategySection;
    onSectionChange: (section: StrategySection) => void;
    userName: string;
    onLogout: () => void;
};

export const Header = ({
                           activeSection,
                           onSectionChange,
                           userName,
                           onLogout,
                       }: HeaderProps) => (
    <Wrapper>
        <Logo />

        <Menu
            activeSection={activeSection}
            onSectionChange={onSectionChange}
        />

        <User>
            <UserName id="header-user-name">{userName}</UserName>
            <SwitchButton
                type="button"
                aria-describedby="header-user-name"
                onClick={onLogout}
            >
                Сменить пользователя
            </SwitchButton>
        </User>
    </Wrapper>
);

const Wrapper = styled.header`
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 18px;
    padding: 12px 2px 2px;

    @media (max-width: 1050px) {
        grid-template-columns: 1fr auto;

        nav {
            grid-column: 1 / -1;
            grid-row: 2;
            justify-self: center;
        }
    }

    @media (max-width: 750px) {
        nav {
            justify-self: stretch;
        }
    }
`;

const User = styled.div`
    position: relative;
    justify-self: end;

    &:hover span,
    &:focus-within span {
        opacity: 1;
        visibility: visible;
        transform: translateY(-50%) translateX(0);
    }
`;

const UserName = styled.span`
    position: absolute;
    top: 50%;
    right: calc(100% + 10px);

    max-width: 240px;
    padding: 11px 16px;
    border-radius: 999px;

    background: rgba(255, 255, 255, 0.6);
    backdrop-filter: blur(16px);

    font: 500 12px ${theme.fonts.interface};
    color: ${theme.colors.darkBgColor};
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;

    opacity: 0;
    visibility: hidden;
    pointer-events: none;
    transform: translateY(-50%) translateX(8px);
    transition: ${theme.animation.transition};
`;

const SwitchButton = styled.button`
    padding: 12px 18px;
    border: 1px solid ${theme.colors.surface};
    border-radius: 999px;
    background: transparent;

    font: 400 12px ${theme.fonts.interface};
    color: ${theme.colors.darkBgColor};
    white-space: nowrap;
    cursor: pointer;

    transition: ${theme.animation.transition};

    &:hover {
        border-color: ${theme.colors.accent};
        color: ${theme.colors.accent};
        background: rgba(255, 255, 255, 0.5);
    }

    &:focus-visible {
        outline: 2px solid ${theme.colors.accent};
        outline-offset: 2px;
    }
`;
