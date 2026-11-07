
export type ApplicationStatus =
    | "approved"
    | "declined"
    | "review";

export type Decision = "approved" | "declined" | "review";

export type RuleChange = {
    name: string;
    before: string;
    after: string;
    reason: string;
};

export type Application = {
    id: string;
    date: string;
    status: ApplicationStatus;
    previousDecision: Decision;
    currentDecision: Decision;
    summary: string;
    changesCount: number;
    changes: RuleChange[];
};
