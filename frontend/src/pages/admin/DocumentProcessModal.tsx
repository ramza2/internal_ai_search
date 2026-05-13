import { createPortal } from "react-dom";
import { Button, SectionCard } from "@/components/ui";
import type { DataSource } from "@/types/dataSource";
import docStyles from "./DocumentProcessModal.module.css";
import { DocumentProcessingPanel } from "./pipeline/DocumentProcessingPanel";

type Props = {
  dataSource: DataSource;
  onClose: () => void;
};

export function DocumentProcessModal({ dataSource, onClose }: Props) {
  return createPortal(
    <div className={docStyles.overlay} role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={docStyles.panel} onMouseDown={(e) => e.stopPropagation()}>
        <SectionCard
          title="문서 파일 처리"
          actions={
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>
              닫기
            </Button>
          }
        >
          <DocumentProcessingPanel
            dataSourceId={dataSource.id}
            dataSourceName={dataSource.name}
            showIntroBullets
            showFollowUpChunkEmbed
          />
        </SectionCard>
      </div>
    </div>,
    document.body
  );
}
