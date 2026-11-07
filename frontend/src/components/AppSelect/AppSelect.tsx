
import {
    useEffect,
    useId,
    useRef,
    useState,
    type KeyboardEvent,
} from 'react';
import styled from 'styled-components';
import { theme } from '../../styles/Theme';

export type AppSelectOption = {
    value: string;
    label: string;
};

type AppSelectProps = {
    value: string;
    options: readonly AppSelectOption[];
    onChange: (value: string) => void;
    ariaLabel: string;
    placeholder?: string;
    disabled?: boolean;
    className?: string;
};

const Root = styled.div<{ $open: boolean }>`
    position: relative;
    z-index: ${({ $open }) => ($open ? 20 : 'auto')};

    display: inline-grid;
    grid-template-columns: minmax(0, 1fr);

    width: 100%;
    min-width: 0;
    max-width: 100%;

    @media (max-width: 640px) {
        width: 100%;
        min-width: 0;
    }
`;

const Sizer = styled.div`
    grid-area: 1 / 1;
    display: grid;

    box-sizing: border-box;
    width: 100%;
    min-width: 0;
    max-width: 100%;
    padding: 0 48px 0 17px;

    overflow: hidden;
    visibility: hidden;
    pointer-events: none;

    span {
        grid-area: 1 / 1;
        width: max-content;
        white-space: nowrap;
        font: 500 13px ${theme.fonts.interface};
    }

    @media (max-width: 640px) {
        min-width: 0;
        max-width: 100%;
    }
`;

const Trigger = styled.button<{ $open: boolean }>`
    grid-area: 1 / 1;
    position: relative;

    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;

    box-sizing: border-box;
    width: 100%;
    min-width: 0;
    height: 46px;
    padding: 0 17px;

    border: 1px solid
    ${({ $open }) => ($open ? theme.colors.accent : '#e5e5e9')};
    border-radius: 15px;

    /* Убираем вторую обводку */
    outline: none;
    box-shadow: none;

    background: #fff;
    color: #202020;

    font: 500 13px ${theme.fonts.interface};
    text-align: left;
    cursor: pointer;

    transition:
            border-color 0.2s ease,
            background 0.2s ease;

    &:hover:not(:disabled) {
        border-color: ${theme.colors.accent};
    }

    &:focus-visible {
        border-color: ${theme.colors.accent};
        outline: none;
    }

    &:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
`;

const Value = styled.span<{ $placeholder: boolean }>`
    flex: 1;
    min-width: 0;

    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;

    color: ${({ $placeholder }) =>
            $placeholder ? '#9696a0' : '#202020'};
`;

const Chevron = styled.span<{ $open: boolean }>`
    flex-shrink: 0;
    width: 8px;
    height: 8px;

    border-right: 1.5px solid #898d99;
    border-bottom: 1.5px solid #898d99;

    transform: ${({ $open }) =>
            $open ? 'rotate(225deg)' : 'rotate(45deg)'};

    transition: transform 0.2s ease;
`;

const Menu = styled.ul`
    position: absolute;
    top: calc(100% + 9px);
    left: 0;
    right: 0;
    z-index: 50;

    box-sizing: border-box;
    margin: 0;
    padding: 6px;
    list-style: none;

    max-height: 270px;
    overflow-y: auto;

    background: rgba(255, 255, 255, 0.98);
    border: 1px solid #efeff1;
    border-radius: 15px;

    box-shadow: 0 15px 35px rgba(35, 35, 45, 0.1);

    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);

    &:focus {
        outline: none;
    }
`;

const Option = styled.li<{
    $selected: boolean;
    $active: boolean;
}>`
    display: flex;
    align-items: center;

    box-sizing: border-box;
    min-height: 42px;
    padding: 10px 12px;

    border-radius: 10px;

    background: ${({ $selected, $active }) =>
            $selected
                    ? '#fff1ed'
                    : $active
                            ? '#f7f7f9'
                            : 'transparent'};

    color: ${({ $selected }) =>
            $selected ? theme.colors.accent : '#303039'};

    font: 400 13px ${theme.fonts.interface};
    line-height: 20px;
    overflow-wrap: anywhere;

    cursor: pointer;

    transition:
            background 0.15s ease,
            color 0.15s ease;
`;

export function AppSelect({
                              value,
                              options,
                              onChange,
                              ariaLabel,
                              placeholder = 'Выберите значение',
                              disabled = false,
                              className,
                          }: AppSelectProps) {
    const [open, setOpen] = useState(false);
    const [activeIndex, setActiveIndex] = useState(0);

    const rootRef = useRef<HTMLDivElement>(null);
    const triggerRef = useRef<HTMLButtonElement>(null);
    const menuRef = useRef<HTMLUListElement>(null);

    const listId = useId();

    const selected = options.find(
        option => option.value === value
    );

    const isDisabled = disabled || options.length === 0;

    useEffect(() => {
        if (open) {
            menuRef.current?.focus();
        }
    }, [open]);

    useEffect(() => {
        if (!open) return;

        menuRef.current?.children
            .item(activeIndex)
            ?.scrollIntoView({ block: 'nearest' });
    }, [activeIndex, open]);

    useEffect(() => {
        if (!open) return;

        function handleOutside(event: PointerEvent) {
            if (
                !rootRef.current?.contains(event.target as Node)
            ) {
                setOpen(false);
            }
        }

        document.addEventListener('pointerdown', handleOutside);

        return () => {
            document.removeEventListener(
                'pointerdown',
                handleOutside
            );
        };
    }, [open]);

    useEffect(() => {
        if (isDisabled) {
            setOpen(false);
        }
    }, [isDisabled]);

    function openMenu() {
        if (isDisabled) return;

        const index = options.findIndex(
            option => option.value === value
        );

        setActiveIndex(Math.max(0, index));
        setOpen(true);
    }

    function choose(nextValue: string) {
        onChange(nextValue);
        setOpen(false);
        triggerRef.current?.focus();
    }

    function handleTriggerKeyDown(
        event: KeyboardEvent<HTMLButtonElement>
    ) {
        if (
            event.key === 'ArrowDown' ||
            event.key === 'ArrowUp'
        ) {
            event.preventDefault();
            openMenu();
        }
    }

    function handleMenuKeyDown(
        event: KeyboardEvent<HTMLUListElement>
    ) {
        switch (event.key) {
            case 'ArrowDown':
                event.preventDefault();
                setActiveIndex(index =>
                    Math.min(index + 1, options.length - 1)
                );
                break;

            case 'ArrowUp':
                event.preventDefault();
                setActiveIndex(index =>
                    Math.max(index - 1, 0)
                );
                break;

            case 'Home':
                event.preventDefault();
                setActiveIndex(0);
                break;

            case 'End':
                event.preventDefault();
                setActiveIndex(options.length - 1);
                break;

            case 'Enter':
            case ' ':
                event.preventDefault();

                if (options[activeIndex]) {
                    choose(options[activeIndex].value);
                }
                break;

            case 'Escape':
                event.preventDefault();
                setOpen(false);
                triggerRef.current?.focus();
                break;

            case 'Tab':
                setOpen(false);
                break;
        }
    }

    return (
        <Root
            ref={rootRef}
            $open={open}
            className={className}
        >
            <Sizer aria-hidden="true">
                <span>{placeholder}</span>

                {options.map(option => (
                    <span key={option.value}>
            {option.label}
          </span>
                ))}
            </Sizer>

            <Trigger
                ref={triggerRef}
                type="button"
                $open={open}
                disabled={isDisabled}
                aria-label={ariaLabel}
                aria-haspopup="listbox"
                aria-expanded={open}
                aria-controls={open ? listId : undefined}
                onKeyDown={handleTriggerKeyDown}
                onClick={() => {
                    if (open) setOpen(false);
                    else openMenu();
                }}
            >
                <Value $placeholder={!selected}>
                    {selected?.label ?? placeholder}
                </Value>

                <Chevron $open={open} aria-hidden="true" />
            </Trigger>

            {open && (
                <Menu
                    ref={menuRef}
                    id={listId}
                    role="listbox"
                    tabIndex={-1}
                    aria-label={ariaLabel}
                    aria-activedescendant={
                        `${listId}-option-${activeIndex}`
                    }
                    onKeyDown={handleMenuKeyDown}
                >
                    {options.map((option, index) => (
                        <Option
                            key={option.value}
                            id={`${listId}-option-${index}`}
                            role="option"
                            aria-selected={option.value === value}
                            $selected={option.value === value}
                            $active={index === activeIndex}
                            onMouseEnter={() => setActiveIndex(index)}
                            onMouseDown={event =>
                                event.preventDefault()
                            }
                            onClick={() => choose(option.value)}
                        >
                            {option.label}
                        </Option>
                    ))}
                </Menu>
            )}
        </Root>
    );
}
