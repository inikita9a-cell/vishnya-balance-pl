
import {
    useId,
    useState,
    type ReactNode,
} from 'react';
import styled from 'styled-components';

type InfoNoticeProps = {
    title: string;
    children: ReactNode;
    defaultOpen?: boolean;
};

const Notice = styled.div`
    padding: 20px 24px;
    border-radius: 16px;
    background: #fcebdd;

    @media (max-width: 640px) {
        padding: 18px;
    }
`;

const Toggle = styled.button`
  display: flex;
  align-items: center;
  gap: 12px;

  width: 100%;
  padding: 0;
  border: none;
  background: transparent;

  font-family: 'Manrope', sans-serif;
  color: #202020;
  text-align: left;
  cursor: pointer;

  &:focus-visible {
    outline: 2px solid #ed9560;
    outline-offset: 5px;
    border-radius: 4px;
  }
`;

const InfoIcon = styled.span`
  display: grid;
  place-items: center;
  flex-shrink: 0;

  width: 24px;
  height: 24px;

  border: 1.5px solid #e87932;
  border-radius: 50%;

  color: #e87932;
  font-size: 13px;
  font-weight: 700;
`;

const NoticeTitle = styled.span`
  flex: 1;

  font-family: 'Manrope', sans-serif;
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
  color: #202020;
`;

const Chevron = styled.span<{ $open: boolean }>`
  width: 9px;
  height: 9px;
  flex-shrink: 0;
  margin-right: 5px;

  border-right: 1.5px solid #a66a44;
  border-bottom: 1.5px solid #a66a44;

  transform: ${({ $open }) =>
    $open ? 'rotate(225deg)' : 'rotate(45deg)'};

  transition: transform 0.35s ease;

  @media (prefers-reduced-motion: reduce) {
    transition: none;
  }
`;

const ContentGrid = styled.div<{ $open: boolean }>`
  display: grid;
  grid-template-rows: ${({ $open }) =>
    $open ? '1fr' : '0fr'};

  transition: grid-template-rows 0.4s
    cubic-bezier(0.22, 1, 0.36, 1);

  @media (prefers-reduced-motion: reduce) {
    transition: none;
  }
`;

const ContentClip = styled.div`
  min-height: 0;
  overflow: hidden;
`;

const Content = styled.div<{ $open: boolean }>`
  padding: 12px 36px 2px;

  font-family: 'Manrope', sans-serif;
  font-size: 13px;
  font-weight: 400;
  line-height: 1.6;
  color: #202020;

  opacity: ${({ $open }) => ($open ? 1 : 0)};

  transform: translateY(
    ${({ $open }) => ($open ? '0' : '-6px')}
  );

  transition:
    opacity 0.3s ease,
    transform 0.35s ease;

  p {
    margin: 0 0 8px;
    font: inherit;
    color: inherit;
  }

  p:last-child {
    margin-bottom: 0;
  }

  @media (max-width: 640px) {
    padding-left: 0;
    padding-right: 0;
  }

  @media (prefers-reduced-motion: reduce) {
    transition: none;
  }
`;

export function InfoNotice({
                               title,
                               children,
                               defaultOpen = true,
                           }: InfoNoticeProps) {
    const [open, setOpen] = useState(defaultOpen);
    const contentId = useId();

    return (
        <Notice>
            <Toggle
                type="button"
                aria-expanded={open}
                aria-controls={contentId}
                onClick={() => setOpen(value => !value)}
            >
                <InfoIcon aria-hidden="true">i</InfoIcon>

                <NoticeTitle>
                    {title}
                </NoticeTitle>

                <Chevron
                    $open={open}
                    aria-hidden="true"
                />
            </Toggle>

            <ContentGrid $open={open}>
                <ContentClip
                    id={contentId}
                    role="region"
                    aria-hidden={!open}
                >
                    <Content $open={open}>
                        {children}
                    </Content>
                </ContentClip>
            </ContentGrid>
        </Notice>
    );
}
