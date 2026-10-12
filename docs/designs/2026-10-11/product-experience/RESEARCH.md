# ASTRA-BIO product experience research

Research checked on 11 October 2026. The goal was to improve a working mission planning workspace with useful interactions, while retaining the selected ASTRA-BIO logo, dark forest/ivory palette, open spacing, and subtle space background.

## Verified award-winning products

| Product | Direct award evidence | Relevant documented pattern | Interpretation for ASTRA-BIO |
| --- | --- | --- | --- |
| Flighty | **2023 Apple Design Award — Interaction**, verified in [Apple's announcement](https://www.apple.com/newsroom/2023/06/apple-announces-winners-of-the-2023-apple-design-awards/). | Apple describes contextual flight information, maps, and forecasts. The [official product site](https://flighty.com/) presents explanations of flight delays. | Put mission context beside the affected result, and connect a scenario event to the day it affects. |
| Crouton | **2024 Apple Design Award — Interaction**, verified in [Apple's announcement](https://www.apple.com/newsroom/2024/06/apple-announces-winners-of-the-2024-apple-design-awards/). | Recipe collection, grocery lists, and sequential cooking instructions support a focused task. | Make scenario setup, running, comparison, and inspection a clear sequence; preserve editable inputs rather than silently running a preset. |
| Lumy | **2024 App Store Award — Apple Watch App of the Year**, verified in [Apple's announcement](https://www.apple.com/newsroom/2024/12/apple-honors-2024-app-store-award-winners/). This is an App Store Award, not an Apple Design Award. | [Apple's editorial](https://apps.apple.com/gb/iphone/story/id1773333753) describes event countdowns, illustrated time context, and tapping a detail to inspect more information. | Let users select a simulation day and see its planned harvest, resource, reserve, and nutrition context. |

Awards verify the recognition above; they do not establish that adopting a pattern will improve this application's usability. These products are interaction references, not biological or mission validation.

## Comparable professional systems

| Primary source | Documented pattern | Application in this revision |
| --- | --- | --- |
| [Priva Operator dashboard features](https://www.priva.com/horticulture/connext-operator-dashboard-features) | Crop, compartment, climate, water, and energy views; shortcuts to settings and detailed measurements. | A connected, open four-node view links crew, food reserve, crops, and resources through the selected saved simulation day. |
| [Grafana dashboard time controls](https://grafana.com/docs/grafana/latest/visualizations/dashboards/use-dashboards/) and [annotation links](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/annotations/) | Explicit time context and event links that focus a graph around an annotation. | A mission-day explorer, selectable event markers, and chart focus show where a planned disruption or harvest sits in the mission. |
| [OneSoil crop planning](https://help.onesoil.ai/en/articles/5235420-how-to-plan-crop-rotation-with-onesoil) | Crop records combine planting/harvest dates, yield, area, and seasonal context. | Planned harvest markers use existing nominal batch dates and link that schedule to daily planning results. |
| [Linear search](https://linear.app/docs/search) and [Linear editor](https://linear.app/docs/editor) | Keyboard-accessible search and a command menu. Search documentation uses `/`; editor documentation explicitly describes the command menu with Cmd/Ctrl K. | Navigation search uses Ctrl/Cmd K to find ten destinations, including food/crop keywords. It searches navigation destinations, not the application's records. |

No award claim is made for these professional comparators. ASTRA-BIO's chosen shortcut and workflow are adaptations, not a reproduction of Linear's complete search behavior.

## Implemented product changes

- **Mission-day explorer:** select a day in the saved run and inspect the corresponding daily values. Markers identify the planned scenario event, nominal harvest dates, and the first recorded nutrient gap.
- **Connected ecosystem:** four open nodes show crew, food reserve, crops, and resources using the saved daily row and nominal batch schedule. This communicates the project's connection without adding another wall of cards.
- **Policy comparison:** show signed absolute whole-run differences from fixed to adaptive planning. Each difference retains its metric, unit, and calculation period; no generalized savings claim is inferred.
- **Chart lenses:** Nutrients, Water, and Electricity views use the existing daily nutrient and resource availability/budget fields, with event/day focus markers.
- **Navigation search:** ten destinations can be found through a visible search control or Ctrl/Cmd K; related food and crop terms also match.
- **Five scenario presets:** prefill editable scenario inputs. Choosing one does not automatically solve a scenario.

The selected logo and space treatment remain the brand layer. The new interactions serve exploration and planning rather than adding visual decoration alone.

## Scope and evidence limits

Official award announcements, public product pages, and primary documentation were reviewed. Flighty's public homepage was also visually reviewed. Authenticated competitor dashboards were not inspected, and this research is not a comparative usability study.

All mission-day results are simulation/planning context. Nominal batch harvest dates remain estimates; they are distinct from realized daily simulated harvest. The connected ecosystem does not constitute measured biological feedback or physical device control. No time-saving, medical, crop-yield, resource-saving, or spaceflight benefit is proven by this UI research.

A crop-batch peek panel and broader contextual drilldown were considered but are **not implemented in this revision**. No new biological model or hardware behavior is implied. Build, automated checks, and browser verification are recorded separately from this research note.
