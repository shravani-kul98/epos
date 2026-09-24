import type { Task, TaskReviewStatus } from "@/types/api";

export const REVIEW_PENDING: TaskReviewStatus = "Pending review";

export function isTaskComplete(task: Task): boolean {
  return ["complete", "completed", "done"].includes(task.status.trim().toLowerCase());
}

export function isTaskClosed(task: Task): boolean {
  return isTaskComplete(task) || ["closed", "cancelled"].includes(task.status.trim().toLowerCase());
}
