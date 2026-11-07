import styled from 'styled-components';
import { theme } from '../styles/Theme';

export const Panel = styled.section`
  background: #fff;
  border: 1px solid #ebebee;
  border-radius: 20px;
  padding: 24px;
  box-shadow: 0 6px 24px rgba(24, 24, 36, .035);
  min-width: 0;
`;

export const PrimaryButton = styled.button`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: ${theme.colors.accent};
  color: #fff;
  border: 1px solid ${theme.colors.accent};
  border-radius: 13px;
  padding: 11px 18px;
  min-height: 43px;
  font: 600 12px ${theme.fonts.interface};
  cursor: pointer;
  transition: ${theme.animation.transition};
  &:hover:not(:disabled) { background: #df5136; border-color: #df5136; }
  &:disabled { opacity: .45; cursor: not-allowed; }
  &:focus-visible { outline: 2px solid ${theme.colors.accent}; outline-offset: 3px; }
`;

export const QuietButton = styled.button`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 43px;
  background: transparent;
  border: 1px solid #dcdce2;
  border-radius: 13px;
  padding: 10px 16px;
  font: 500 12px ${theme.fonts.interface};
  color: ${theme.colors.darkBgColor};
  cursor: pointer;
  transition: ${theme.animation.transition};
  &:hover:not(:disabled) { border-color: ${theme.colors.accent}; color: ${theme.colors.accent}; background: rgba(255,255,255,.65); }
  &:disabled { opacity: .4; cursor: not-allowed; }
  &:focus-visible { outline: 2px solid ${theme.colors.accent}; outline-offset: 3px; }
`;

export const TextButton = styled.button`
  border: 0;
  background: transparent;
  padding: 5px 0;
  color: ${theme.colors.darkBgColor};
  font: 500 12px ${theme.fonts.interface};
  cursor: pointer;
  transition: color .2s ease;
  &:hover:not(:disabled) { color: ${theme.colors.accent}; }
  &:disabled { opacity: .4; cursor: not-allowed; }
  &:focus-visible { outline: 2px solid ${theme.colors.accent}; outline-offset: 3px; border-radius: 3px; }
`;

export const Field = styled.input`
  width: 100%;
  background: #fff;
  border: 1px solid #e5e5e9;
  border-radius: 15px;
  min-height: 46px;
  padding: 12px 16px;
  font: 500 13px ${theme.fonts.interface};
  outline: none;
  transition: border-color .2s ease;
  &:focus { border-color: ${theme.colors.accent}; }
`;

export const SelectField = styled.select`
  background: #fff;
  border: 1px solid #e5e5e9;
  border-radius: 15px;
  min-height: 46px;
  padding: 12px 16px;
  font: 500 13px ${theme.fonts.interface};
  outline: none;
  min-width: 180px;
  &:focus { border-color: ${theme.colors.accent}; }
`;

export const PageHeading = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 24px;
  h1 { font-size: clamp(20px, 2.3vw, 25px); line-height: 1.35; letter-spacing: -.8px; }
  p { font-size: 13px; color: #858591; margin-top: 8px; font-weight: 500; }
`;

export const Line = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
`;

export const DataTable = styled.table`
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font: 400 12px ${theme.fonts.primary};
  font-variant-numeric: tabular-nums;
  th {
    background: #fafafb;
    padding: 15px 16px;
    color: #898993;
    font-size: 11px;
    font-weight: 650;
    letter-spacing: .025em;
    text-transform: uppercase;
    white-space: nowrap;
  }
  td { border-top: 1px solid #eeeef1; padding: 15px 16px; vertical-align: middle; }
  tbody tr:hover { background: #fafafb; }
  td:first-child, th:first-child { padding-left: 24px; }
  td:last-child, th:last-child { padding-right: 24px; }
`;

export const TableScroller = styled.div`
  width: 100%;
  overflow-x: auto;
`;

export const Muted = styled.span`
  color: #8e8e99;
  font: 400 12px ${theme.fonts.interface};
`;

export const ErrorBox = styled.div`
  padding: 12px 15px;
  background: #fff1ed;
  color: #a43424;
  border: 1px solid #ffd5c8;
  border-radius: 12px;
  font-size: 13px;
  margin: 12px 0;
`;

export const Empty = styled.div`
  padding: 36px;
  text-align: center;
  color: #888894;
  font-size: 13px;
`;

export const Tag = styled.span<{ $tone?: 'good' | 'busy' | 'bad' }>`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: ${p => p.$tone === 'good' ? '#278259' : p.$tone === 'bad' ? '#c45343' : '#b47b36'};
  font: 500 12px ${theme.fonts.interface};
  white-space: nowrap;
  &::before { content: ''; width: 7px; height: 7px; background: currentColor; border-radius: 50%; }
`;

export const NoticeSpacing = styled.div` margin-bottom: 22px; `;
