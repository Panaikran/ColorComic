import unittest


class MangaNinjaUNetConfigTests(unittest.TestCase):
    def test_denoising_unet_accepts_diffusers_configs_without_num_attention_heads(self):
        from vendor.manganinja.models.unet_2d_condition import UNet2DConditionModel

        model = UNet2DConditionModel(
            block_out_channels=(32, 64),
            down_block_types=("CrossAttnDownBlock2D", "DownBlock2D"),
            up_block_types=("UpBlock2D", "CrossAttnUpBlock2D"),
            cross_attention_dim=32,
            norm_num_groups=8,
            attention_head_dim=8,
            num_attention_heads=None,
        )

        self.assertEqual(len(model.down_blocks), 2)

    def test_reference_unet_accepts_diffusers_configs_without_num_attention_heads(self):
        from vendor.manganinja.models.refunet_2d_condition import RefUNet2DConditionModel

        model = RefUNet2DConditionModel(
            block_out_channels=(32, 64),
            down_block_types=("CrossAttnDownBlock2D", "DownBlock2D"),
            up_block_types=("UpBlock2D", "CrossAttnUpBlock2D"),
            cross_attention_dim=32,
            norm_num_groups=8,
            attention_head_dim=8,
            num_attention_heads=None,
        )

        self.assertEqual(len(model.down_blocks), 2)

    def test_transformer_uses_conv_projections_by_default_for_sd_checkpoints(self):
        from vendor.manganinja.models.transformer_2d import Transformer2DModel

        model = Transformer2DModel(
            num_attention_heads=4,
            attention_head_dim=8,
            in_channels=32,
            cross_attention_dim=32,
            norm_num_groups=8,
            use_linear_projection=False,
        )

        self.assertEqual(tuple(model.proj_in.weight.shape), (32, 32, 1, 1))
        self.assertEqual(tuple(model.proj_out.weight.shape), (32, 32, 1, 1))

    def test_lineart_checkpoint_keys_are_mapped_to_vendored_generator_layout(self):
        from vendor.manganinja.annotator.lineart import normalize_lineart_state_dict

        state = {
            "model0.1.weight": "initial",
            "model1.0.weight": "down_1",
            "model1.3.weight": "down_2",
            "model2.0.conv_block.1.weight": "res_1",
            "model3.0.weight": "up_1",
            "model3.3.weight": "up_2",
            "model4.1.weight": "output",
        }

        self.assertEqual(
            normalize_lineart_state_dict(state),
            {
                "model.1.weight": "initial",
                "model.4.weight": "down_1",
                "model.7.weight": "down_2",
                "model.10.block.1.weight": "res_1",
                "model.13.weight": "up_1",
                "model.16.weight": "up_2",
                "model.20.weight": "output",
            },
        )

    def test_pipeline_expands_single_clip_embedding_to_text_sequence_length(self):
        import torch

        from vendor.manganinja.pipeline import match_sequence_length

        hidden_states = torch.ones((1, 1, 4))
        matched = match_sequence_length(hidden_states, 77)

        self.assertEqual(tuple(matched.shape), (1, 77, 4))
        self.assertTrue(torch.equal(matched[:, 0, :], hidden_states[:, 0, :]))
        self.assertTrue(torch.equal(matched[:, -1, :], hidden_states[:, 0, :]))

    def test_pipeline_keeps_controlnet_condition_three_channel(self):
        import torch

        from vendor.manganinja.pipeline import prepare_controlnet_condition

        condition = torch.zeros((1, 3, 512, 512))
        prepared = prepare_controlnet_condition(condition, batch_size=3)

        self.assertEqual(tuple(prepared.shape), (3, 3, 512, 512))


if __name__ == "__main__":
    unittest.main()
