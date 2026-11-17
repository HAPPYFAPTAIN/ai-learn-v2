import { createContext, useContext } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation, useSearchParams } from "react-router-dom";
import { endpoints, type Project } from "../api";
import { key } from "../query";
export const ProjectContext = createContext<{
  id: number;
  project?: Project;
  projects: Project[];
}>({ id: 0, projects: [] });
export const useProject = () => useContext(ProjectContext);
export function useProjects() {
  const [params] = useSearchParams();
  const { pathname } = useLocation();
  const query = useQuery({
    queryKey: key("projects"),
    queryFn: ({ signal }) => endpoints.projects(signal),
  });
  const projects = query.data?.items || [];
  const raw = params.get("project");
  const selected = raw
    ? projects.find((p) => String(p.id) === raw)
    : pathname === "/study"
      ? undefined
      : projects[0];
  return {
    query,
    value: { id: selected?.id || 0, project: selected, projects },
    invalid: !!raw && !!query.data && !selected,
  };
}
