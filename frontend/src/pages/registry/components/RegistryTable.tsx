
import styled from "styled-components";

import { theme } from "../../../styles/Theme.ts";
import type { Application } from "../types.ts";

type RegistryTable = {
    applications: Application[];
    selectedId: string | null;
    onSelect: (id: string) => void;
};

const decisions = {
    approved: "Одобрено",
    declined: "Отказ",
    review: "Не определено",
};

const statuses = {
    approved: "Одобрено",
    declined: "Отказ",
    review: "На проверке",
};

const formatChanges = (count: number) => {
    if (count === 0) return "Нет";

    const last = count % 10;
    const lastTwo = count % 100;

    const word = lastTwo >= 11 && lastTwo <= 14
        ? "параметров"
        : last === 1
            ? "параметр"
            : last >= 2 && last <= 4
                ? "параметра"
                : "параметров";

    return `${count} ${word}`;
};

export const RegistryTable = ({
                                  applications,
                                  selectedId,
                                  onSelect,
                              }: RegistryTable) => {
    return (
        <TableWrapper>
            <TableHeader>
                <TableTitle>Реестр заявок</TableTitle>
                <TableCount>
                    {applications.length} записей
                </TableCount>
            </TableHeader>

            <TableScroll>
                <Table>
                    <colgroup>
                        <col style={{ width: "18%" }} />
                        <col style={{ width: "13%" }} />
                        <col style={{ width: "18%" }} />
                        <col style={{ width: "18%" }} />
                        <col style={{ width: "17%" }} />
                        <col style={{ width: "16%" }} />
                    </colgroup>

                    <thead>
                    <tr>
                        <th scope="col">Идентификатор заявки</th>
                        <th scope="col">Дата</th>
                        <th scope="col">Исходная стратегия</th>
                        <th scope="col">Новая стратегия</th>
                        <th scope="col">Изменённые параметры</th>
                        <th scope="col">Статус заявки</th>
                    </tr>
                    </thead>

                    <tbody>
                    {applications.map(application => {
                        const selected =
                            selectedId === application.id;

                        const decisionChanged =
                            application.previousDecision !==
                            application.currentDecision;

                        const changeCount =
                            application.changesCount;

                        const changeText =
                            decisionChanged && changeCount === 0
                                ? "Не указаны"
                                : formatChanges(changeCount);

                        return (
                            <TableRow
                                key={application.id}
                                data-selected={selected}
                                onClick={() =>
                                    onSelect(application.id)
                                }
                            >
                                <td>
                                    <ApplicationButton
                                        type="button"
                                        aria-expanded={selected}
                                        aria-label={`Сведения по заявке ${application.id}`}
                                    >
                                        {application.id}
                                    </ApplicationButton>
                                </td>

                                <td>
                                    <SecondaryText>
                                        {application.date}
                                    </SecondaryText>
                                </td>

                                <td>
                                    {decisions[
                                        application.previousDecision
                                        ]}
                                </td>

                                <td>
                                    {decisions[
                                        application.currentDecision
                                        ]}
                                </td>

                                <td>
                                    <ChangeText
                                        data-changed={changeCount > 0}
                                    >
                                        {changeText}
                                    </ChangeText>
                                </td>

                                <td>
                                    <SecondaryText>
                                        {statuses[application.status]}
                                    </SecondaryText>
                                </td>
                            </TableRow>
                        );
                    })}

                    {applications.length === 0 && (
                        <tr>
                            <EmptyCell colSpan={6}>
                                Заявки не найдены
                            </EmptyCell>
                        </tr>
                    )}
                    </tbody>
                </Table>
            </TableScroll>
        </TableWrapper>
    );
};

const TableWrapper = styled.div`
    width: 100%;
    min-width: 0;
    overflow: hidden;

    //border: 1px solid #e5e5e8;
    border-radius: 20px;
    background: ${theme.colors.fontLight};
`;

const TableHeader = styled.div`
    display: flex;
    align-items: center;
    justify-content: space-between;

    min-height: 60px;
    padding: 0 24px;

    border-bottom: 1px solid #eeeeef;
`;

const TableTitle = styled.h2`
    color: ${theme.colors.darkBgColor};
    font-family: ${theme.fonts.primary};
    font-size: 15px;
    font-weight: 600;
`;

const TableCount = styled.span`
    color: ${theme.colors.textMuted};
    font-size: 12px;
`;

const TableScroll = styled.div`
    width: 100%;
    overflow-x: auto;
`;

const Table = styled.table`
    width: 100%;
    min-width: 920px;

    table-layout: fixed;
    border-collapse: collapse;
    text-align: left;

    font-family: ${theme.fonts.primary};
    font-size: 12px;
    font-variant-numeric: tabular-nums;

    th {
        height: 48px;
        padding: 12px 20px;

        background: #fafafb;
        border-bottom: 1px solid #eeeeef;

        color: ${theme.colors.textMuted};
        font-size: 12px;
        font-weight: 500;
        white-space: nowrap;
    }

    td {
        height: 60px;
        padding: 14px 20px;

        border-bottom: 1px solid #f0f0f2;

        color: ${theme.colors.darkBgColor};
        vertical-align: middle;
        white-space: nowrap;
    }

    tbody tr:last-child td {
        border-bottom: none;
    }

    th:first-child,
    td:first-child {
        padding-left: 24px;
    }

    th:last-child,
    td:last-child {
        padding-right: 24px;
    }
`;

const TableRow = styled.tr`
    cursor: pointer;

    td {
        transition: background-color 0.15s ease;
    }

    &:hover td {
        background: #f8f8f9;
    }

    &[data-selected="true"] td {
        background: ${theme.colors.accent}0D;
    }

    &:focus-within td {
        background: ${theme.colors.accent}0D;
    }
`;

const ApplicationButton = styled.button`
    padding: 0;
    border: none;
    background: transparent;

    color: ${theme.colors.darkBgColor};
    font: inherit;
    font-weight: 600;

    cursor: pointer;

    &:focus-visible {
        outline: 2px solid ${theme.colors.accent};
        outline-offset: 4px;
        border-radius: 2px;
    }
`;

const SecondaryText = styled.span`
    color: #777780;
`;

const ChangeText = styled.span`
    color: ${theme.colors.textMuted};

    &[data-changed="true"] {
        color: ${theme.colors.accent};
        font-weight: 500;
    }
`;

const EmptyCell = styled.td`
    height: 120px !important;
    text-align: center;
    color: ${theme.colors.textMuted} !important;
`;
