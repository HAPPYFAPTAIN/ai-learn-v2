import {
  createContext,
  useContext,
  useEffect,
  type Dispatch,
  type SetStateAction,
} from "react";
export type AssistantPageContext = {
  cardId?: number;
  questionId?: number;
  title?: string;
};
export const AssistantContext = createContext<Dispatch<
  SetStateAction<AssistantPageContext>
> | null>(null);
export function useAssistantPageContext({
  cardId,
  questionId,
  title,
}: AssistantPageContext) {
  const set = useContext(AssistantContext);
  useEffect(() => {
    set?.({ cardId, questionId, title });
    return () => set?.({});
  }, [set, cardId, questionId, title]);
}
