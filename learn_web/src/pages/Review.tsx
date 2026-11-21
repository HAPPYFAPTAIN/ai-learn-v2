import { useAssistantPageContext } from "../components/AssistantContext";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "../api";
import { key } from "../query";
import { useProject } from "../components/ProjectContext";
import AssessmentGenerator from "../components/AssessmentGenerator";
import CardLibrary from "../components/CardLibrary";
import {
  Empty,
  ErrorNotice,
  Icon,
  PageHeading,
  QueryState,
} from "../components/ui";
const nextReviewLabel = (value: string | null) =>
  value ? new Date(value).toLocaleString("zh-CN") : "待安排";
export default function Review() {
  const { projects, id } = useProject();
  const client = useQueryClient();
  const [revealedId, reveal] = useState<number>();
  const cards = useQuery({
    queryKey: key("due"),
    queryFn: ({ signal }) => endpoints.dueCards(signal),
    enabled: !!projects.length,
  });
  const card = cards.data?.items[0];
  useAssistantPageContext({ cardId: card?.id, title: card?.front });
  const revealed = !!card && revealedId === card.id;
  const allCards = useQuery({
    queryKey: key("cards", id),
    queryFn: ({ signal }) => endpoints.cards(id, signal),
    enabled: !!id,
  });
  const rate = useMutation({
    mutationFn: (rating: number) =>
      endpoints.review(card!.id, rating, card!.reps),
    onSuccess: async () => {
      reveal(undefined);
      await client.invalidateQueries({ queryKey: key("due") });
      await client.invalidateQueries({ queryKey: key("cards", id) });
      await client.invalidateQueries({ queryKey: key("nodes") });
    },
  });
  return (
    <>
      <PageHeading
        title="间隔复习"
        description="在恰好的时间温习，让记忆更牢固。涵盖当前账号全部学习计划。"
        action={
          id ? (
            <AssessmentGenerator key={id} projectId={id} kind="cards" />
          ) : undefined
        }
      />
      {!projects.length ? (
        <Empty title="暂无学习目标" />
      ) : (
        <>
          {rate.data && (
            <p className="notice" role="status">
              复习记录已保存，下次复习：
              {nextReviewLabel(rate.data.nextReview)}。
            </p>
          )}
          <QueryState query={cards} />
          {cards.data &&
            (card ? (
              <div className="panel review-panel" key={card.id}>
                <span className="badge">
                  待复习 {cards.data.items.length} 张
                </span>
                <div className="review-content">
                  <div className="empty-icon">
                    <Icon name="review" size={26} />
                  </div>
                  <p className="eyebrow">先回忆，再查看答案</p>
                  <h2>{card.front}</h2>
                  {revealed && <div className="review-answer">{card.back}</div>}
                </div>
                {!revealed ? (
                  <button className="primary" onClick={() => reveal(card.id)}>
                    查看答案
                  </button>
                ) : (
                  <>
                    <p className="muted">你记得怎么样？</p>
                    <div className="rating-row">
                      {["重来", "有点难", "记得", "很熟"].map((t, i) => (
                        <button
                          key={t}
                          disabled={rate.isPending}
                          onClick={() => rate.mutate(i + 1)}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                  </>
                )}
                <ErrorNotice error={rate.error} />
              </div>
            ) : (
              <Empty
                title="今日复习已完成"
                description="暂无到期卡片，给记忆一点沉淀的时间。"
                action={false}
              />
            ))}
          <section className="panel review-schedule">
            <QueryState query={allCards} />
            {allCards.data && (
              <CardLibrary
                key={id}
                projectId={id}
                cards={allCards.data.items}
              />
            )}
          </section>
        </>
      )}
    </>
  );
}
