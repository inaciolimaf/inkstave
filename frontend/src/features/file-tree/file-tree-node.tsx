import { MoreHorizontal } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

import { DisclosureChevron, EntityIcon } from "./entity-icon";
import { useFileTreeContext } from "./file-tree-context";
import { sortNodes } from "./tree-utils";
import type { TreeNode } from "./types";
import { validateEntityName } from "./validate-name";

function InlineRenameInput({ node }: { node: TreeNode }) {
  const ctx = useFileTreeContext();
  const [value, setValue] = useState(node.name);
  const error = validateEntityName(value);

  const commit = () => {
    if (!error) ctx.onCommitRename(node.id, value.trim());
  };

  return (
    <span className="flex flex-1 items-center gap-1">
      <input
        autoFocus
        aria-label="New name"
        aria-invalid={error ? true : undefined}
        className="h-6 w-full rounded border border-input bg-background px-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onFocus={(e) => e.target.select()}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Enter") commit();
          if (e.key === "Escape") ctx.onCancelRename();
        }}
        onBlur={commit}
      />
      {error && (
        <span role="alert" className="whitespace-nowrap text-xs text-destructive">
          {error}
        </span>
      )}
    </span>
  );
}

function NodeMenuItems({
  node,
  Item,
  Separator,
}: {
  node: TreeNode;
  Item: typeof DropdownMenuItem | typeof ContextMenuItem;
  Separator: typeof DropdownMenuSeparator | typeof ContextMenuSeparator;
}) {
  const ctx = useFileTreeContext();
  const isFolder = node.type === "folder";
  return (
    <>
      {isFolder && (
        <>
          <Item onSelect={() => ctx.onMenuAction("new-doc", node)}>New file</Item>
          <Item onSelect={() => ctx.onMenuAction("new-folder", node)}>New folder</Item>
          <Item onSelect={() => ctx.onMenuAction("upload", node)}>Upload here</Item>
          <Separator />
        </>
      )}
      <Item onSelect={() => ctx.onMenuAction("rename", node)}>Rename</Item>
      {node.parentId !== ctx.rootId && (
        <Item onSelect={() => ctx.onMenuAction("move-root", node)}>Move to root</Item>
      )}
      <Separator />
      <Item
        onSelect={() => ctx.onMenuAction("delete", node)}
        className="text-destructive focus:text-destructive"
      >
        Delete
      </Item>
    </>
  );
}

export function FileTreeNode({ node, depth }: { node: TreeNode; depth: number }) {
  const ctx = useFileTreeContext();
  const isFolder = node.type === "folder";
  const expanded = ctx.expandedIds.has(node.id);
  const selected = ctx.selectedId === node.id;
  const focused = ctx.focusedId === node.id;
  const renaming = ctx.renamingId === node.id;
  const isDropTarget = ctx.dropTargetId === node.id;

  const folderDnd = isFolder
    ? {
        onDragOver: (e: React.DragEvent) => {
          e.preventDefault();
          e.stopPropagation();
          ctx.onDragEnterNode(node);
        },
        onDrop: (e: React.DragEvent) => {
          e.preventDefault();
          e.stopPropagation();
          ctx.onDropOnNode(node);
        },
      }
    : {};

  return (
    <li
      role="treeitem"
      aria-level={depth + 1}
      aria-selected={selected}
      aria-expanded={isFolder ? expanded : undefined}
      tabIndex={focused ? 0 : -1}
      ref={(el) => ctx.registerRow(node.id, el)}
      className="outline-none"
    >
      <ContextMenu>
        <ContextMenuTrigger asChild>
          <div
            draggable={!renaming}
            onDragStart={(e) => {
              e.dataTransfer.setData("text/plain", node.id);
              ctx.onDragStart(node.id);
            }}
            onDragEnd={ctx.onDragEnd}
            {...folderDnd}
            onClick={() => ctx.onSelect(node)}
            onDoubleClick={() => ctx.onActivate(node)}
            style={{ paddingLeft: `${depth * 16 + 4}px` }}
            className={cn(
              "group flex h-7 items-center gap-1 rounded px-1 text-sm",
              "focus-visible:ring-1 focus-visible:ring-ring",
              selected && "bg-accent text-accent-foreground",
              focused && !selected && "bg-muted",
              isDropTarget && "ring-1 ring-primary",
            )}
          >
            {isFolder ? (
              <button
                type="button"
                aria-label={expanded ? "Collapse folder" : "Expand folder"}
                className="flex size-4 items-center justify-center"
                onClick={(e) => {
                  e.stopPropagation();
                  ctx.onToggle(node.id);
                }}
              >
                <DisclosureChevron expanded={expanded} />
              </button>
            ) : (
              <span className="size-4" aria-hidden />
            )}
            <EntityIcon type={node.type} />
            {renaming ? (
              <InlineRenameInput node={node} />
            ) : (
              <span className="flex-1 truncate">{node.name}</span>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Actions for ${node.name}`}
                  className="size-6 opacity-0 focus:opacity-100 group-hover:opacity-100"
                  onClick={(e) => e.stopPropagation()}
                >
                  <MoreHorizontal className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" onCloseAutoFocus={(e) => e.preventDefault()}>
                <NodeMenuItems
                  node={node}
                  Item={DropdownMenuItem}
                  Separator={DropdownMenuSeparator}
                />
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </ContextMenuTrigger>
        <ContextMenuContent onCloseAutoFocus={(e) => e.preventDefault()}>
          <NodeMenuItems node={node} Item={ContextMenuItem} Separator={ContextMenuSeparator} />
        </ContextMenuContent>
      </ContextMenu>

      {isFolder && expanded && node.children.length > 0 && (
        <ul role="group">
          {sortNodes(node.children).map((child) => (
            <FileTreeNode key={child.id} node={child} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}
