import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DeliveryTimeline } from "@/components/charts/delivery-timeline";
import { MilestoneTimeline } from "@/components/charts/milestone-timeline";
import type { Milestone, Task } from "@/types/api";

const milestone: Milestone={milestone_id:"M-TEST",project_id:"P-TEST",milestone_name:"Recorded release",baseline_date:"2026-08-01",forecast_date:"2026-08-02",actual_date:"2026-08-02",forecast_variance_days:17,actual_variance_days:1,status:"Completed",criticality:"High",owner:"Synthetic Owner"};
const task: Task={task_id:"T-TEST",project_id:"P-TEST",milestone_id:"M-TEST",deliverable_id:null,parent_task_id:null,task_name:"Recorded work",owner:null,owner_user_id:null,status:"In Progress",planned_start_date:null,forecast_start_date:null,actual_start_date:null,planned_end_date:"2026-08-01",forecast_end_date:"2026-08-02",actual_end_date:null,forecast_start_variance_days:null,forecast_finish_variance_days:1,actual_start_variance_days:null,actual_finish_variance_days:null,completion_percent:20,is_blocked:false,last_updated_date:null,review_required:false,review_status:null,reviewed_by:null,reviewed_at:null,review_note:null};

describe("Delivery timeline",()=>{
  it("does not infer a missing start or duration and supplies all dates as a table",()=>{
    render(<DeliveryTimeline milestones={[milestone]} tasks={[task]} asOfDate="2026-08-25"/>);
    expect(screen.getAllByRole("img")[1]).toHaveAccessibleName(/start not recorded/);
    expect(screen.getByRole("table",{hidden:true})).toHaveTextContent("T-TEST");
    expect(screen.getByText("View timeline dates as table")).toBeInTheDocument();
  });
  it("preserves API variance and does not call completed work overdue",()=>{
    render(<MilestoneTimeline milestones={[milestone]} asOfDate="2026-09-04"/>);
    expect(screen.getByText("17 days late")).toBeInTheDocument();
    expect(screen.queryByText(/Forecast date passed/)).not.toBeInTheDocument();
  });
  it("states when no recorded date can support a timeline",()=>{
    render(<DeliveryTimeline milestones={[]} tasks={[]} asOfDate="2026-08-25"/>);
    expect(screen.getByText(/No recorded dates are available/)).toBeInTheDocument();
  });
});