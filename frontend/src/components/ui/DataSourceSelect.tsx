import { FormField } from "./FormField";
import { Select } from "./Select";

export function DataSourceSelect({
  label = "데이터 소스",
  hint = "활성 소스만 선택됩니다.",
  value,
  onChange,
  items,
  disabled,
}: {
  label?: string;
  hint?: string;
  value: string;
  onChange: (next: string) => void;
  items: Array<{ id: string; name: string; is_active?: boolean }>;
  disabled?: boolean;
}) {
  const options = items.filter((i) => i.is_active !== false);
  return (
    <FormField label={label} hint={hint}>
      <Select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
        <option value="">전체</option>
        {options.map((ds) => (
          <option key={ds.id} value={ds.id}>
            {ds.name}
          </option>
        ))}
      </Select>
    </FormField>
  );
}
