import Select from "./Select";

type Props = {
  projects: { id: number; title: string }[];
  value: number;
  onChange: (id: number) => void;
};
export default function ProjectPicker({ projects, value, onChange }: Props) {
  return (
    <Select
      className="project-picker"
      label="当前学习计划"
      listLabel="学习计划"
      placeholder={projects.length ? "选择学习计划" : "暂无学习计划"}
      options={projects.map((project) => ({
        value: project.id,
        label: project.title,
      }))}
      value={value}
      onChange={onChange}
    />
  );
}
